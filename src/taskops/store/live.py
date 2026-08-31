"""live.sqlite — leases and presence. Alive, not derived, never replicated.

A separate file from the cache on purpose: deleting the derived cache must
never be able to drop a live claim (v1's bug #1 — they shared a database).

The lease IS the mutex, and the mutex is a PRIMARY KEY:
`INSERT OR IGNORE INTO leases(task, ...)` — one row, one winner, decided by
SQLite and not by a prompt. Every call from an actor renews the leases it
holds; a worker whose process died stops renewing and its card surfaces in
the SILENT group of the board.
"""

from __future__ import annotations

import sqlite3
from typing import Any
from pathlib import Path

from .._errors import TaskopsError
from ..core.types import ANON, LEASE_TTL, Lease

DDL = """
CREATE TABLE IF NOT EXISTS leases (
    task     TEXT PRIMARY KEY,   -- the PK is the mutex
    actor    TEXT NOT NULL,
    branch   TEXT NOT NULL,
    acquired REAL NOT NULL,
    expires  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS presence (
    actor TEXT PRIMARY KEY,
    seen  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews (
    task     TEXT PRIMARY KEY,   -- the PK is the mutex, same as leases
    actor    TEXT NOT NULL,
    acquired REAL NOT NULL,
    expires  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS mirror (
    forge TEXT PRIMARY KEY, ok INTEGER NOT NULL, at REAL NOT NULL, detail TEXT NOT NULL
);
"""
# `reviews` is the REVIEW lease — a second mutex per card. Why it is its own
# table, and the whole race analysis, is `store/reviews.py`, which also holds
# its operations. It is created here because the file is opened here.
# `mirror` is the OUTBOUND leg's last word, one row per declared forge:
# `store/mirroring.py` holds its operations and argues why it is not an event.

Row = tuple[Any, ...]


class Live:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.db = sqlite3.connect(path, check_same_thread=False)
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.executescript(DDL)
            self.db.commit()
        except sqlite3.Error as err:
            raise TaskopsError(f"cannot open the live store at {path}: {err}") from err

    def acquire(
        self, task: str, actor: str, branch: str, now: float, ttl: float = LEASE_TTL
    ) -> Lease | None:
        """Atomically claim `task`, or return None because somebody else holds it."""
        try:
            with self.db:
                self.db.execute("DELETE FROM leases WHERE task = ? AND expires <= ?", (task, now))
                cursor = self.db.execute(
                    "INSERT OR IGNORE INTO leases (task, actor, branch, acquired, expires)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (task, actor, branch, now, now + ttl),
                )
                if cursor.rowcount != 1:  # somebody already owns the row
                    held: list[Row] = self.db.execute(
                        "SELECT actor FROM leases WHERE task = ?", (task,)
                    ).fetchall()
                    if not held or str(held[0][0]) != actor:
                        return None
                    self.db.execute(  # the holder re-taking its own card: renew
                        "UPDATE leases SET expires = ?, branch = ? WHERE task = ?",
                        (now + ttl, branch, task),
                    )
        except sqlite3.Error as err:
            raise TaskopsError(f"live store: cannot claim {task}: {err}") from err
        return self.lease(task, now)

    def lease(self, task: str, now: float) -> Lease | None:
        rows = self._query(
            "SELECT task, actor, branch, acquired, expires FROM leases"
            " WHERE task = ? AND expires > ?",
            (task, now),
        )
        return _lease(rows[0]) if rows else None

    def holder(self, task: str, now: float) -> str | None:
        lease = self.lease(task, now)
        return lease["actor"] if lease else None

    def renew(self, actor: str, now: float, ttl: float = LEASE_TTL) -> None:
        """Any call from `actor` proves it is alive — that is the whole heartbeat.
        Review leases renew by the same rule: the traffic is the heartbeat.

        **`anon` renews NOTHING, and this is the one place that decides it.**
        Every read verb opens with `renew(actor)` — six call sites today
        (`pulse`, `card`, `report`, `events`, plus the two writes' own) — so a
        public board's anonymous reader would INSERT a presence row on every
        page load: a write caused by a stranger's question, the milestone's
        second rule broken by the most ordinary request there is. Guarding the
        six callers instead is the shape of v1's bug (`verbs/__init__.py`'s
        docstring: one decision re-taken at 25 sites, four of them differently)
        — a seventh read verb would be written next month by somebody who never
        read this file. Here it cannot be forgotten: `anon` holds no lease by
        construction (`take` is a write and a write is refused before it gets
        here), so there is nothing this call could legitimately do for it.
        """
        if actor == ANON:
            return
        self._write(
            [
                (
                    "UPDATE leases SET expires = ? WHERE actor = ? AND expires > ?",
                    (now + ttl, actor, now),
                ),
                (
                    "UPDATE reviews SET expires = ? WHERE actor = ? AND expires > ?",
                    (now + ttl, actor, now),
                ),
                (
                    "INSERT INTO presence (actor, seen) VALUES (?, ?)"
                    " ON CONFLICT(actor) DO UPDATE SET seen = excluded.seen",
                    (actor, now),
                ),
            ]
        )

    def release(self, task: str, actor: str) -> bool:
        """Give the card back. Only the holder can — there is no force variant,
        because there is no recover: an abandoned lease simply expires."""
        try:
            with self.db:
                cursor = self.db.execute(
                    "DELETE FROM leases WHERE task = ? AND actor = ?", (task, actor)
                )
                return cursor.rowcount == 1
        except sqlite3.Error as err:
            raise TaskopsError(f"live store: cannot release {task}: {err}") from err

    def held(self, now: float) -> list[Lease]:
        return [
            _lease(r) for r in self._query(_ALL + " WHERE expires > ? ORDER BY acquired", (now,))
        ]

    def lapsed(self, now: float) -> list[Lease]:
        """Rows whose holder stopped renewing — the SILENT group of the board."""
        return [
            _lease(r) for r in self._query(_ALL + " WHERE expires <= ? ORDER BY expires", (now,))
        ]

    def present(self, since: float) -> list[tuple[str, float]]:
        rows = self._query(
            "SELECT actor, seen FROM presence WHERE seen >= ? ORDER BY seen", (since,)
        )
        return [(str(r[0]), float(r[1])) for r in rows]

    def close(self) -> None:
        self.db.close()

    def _query(self, sql: str, args: Row = ()) -> list[Row]:
        try:
            rows: list[Row] = self.db.execute(sql, args).fetchall()
        except sqlite3.Error as err:
            raise TaskopsError(f"live store: {err}") from err
        return rows

    def _write(self, statements: list[tuple[str, Row]]) -> None:
        try:
            with self.db:
                for sql, args in statements:
                    self.db.execute(sql, args)
        except sqlite3.Error as err:
            raise TaskopsError(f"live store: {err}") from err


_ALL = "SELECT task, actor, branch, acquired, expires FROM leases"


def _lease(row: Row) -> Lease:
    return Lease(
        task=str(row[0]),
        actor=str(row[1]),
        branch=str(row[2]),
        acquired=float(row[3]),
        expires=float(row[4]),
    )
