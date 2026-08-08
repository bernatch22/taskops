"""The review lease — a second mutex per card, in its own table of live.sqlite.

A SEPARATE table, not a `purpose` column on `leases`: changing the PK of
`leases` needs a SQLite table rebuild, and live.sqlite is the one file in this
system that is not disposable. `CREATE TABLE IF NOT EXISTS` (in `live.DDL`) is
purely additive — an existing board gains it with no migration.

A card can hold a work lease and a review lease at once, held by different
actors: the worker deliberately stays alive while the verifier reads. And if
two verifiers somehow both review, nothing corrupts: verdicts are appended
events (content-addressed, so identical ones dedupe), and the close guard
demands a `pass` while showing the whole thread — the worst case is wasted
tokens, never a card closed unreviewed. A verifier that dies simply stops
renewing; its lease lapses and the card returns to `review` on its own. There
is no recover for reviews either.

These are functions over `Live.db` rather than methods so `live.py` stays
inside the 200-line budget along a seam, not an arbitrary cut.
"""

from __future__ import annotations

import sqlite3
from typing import NamedTuple

from .live import Row, Live
from .._errors import TaskopsError
from ..core.types import LEASE_TTL


def claim(live: Live, task: str, actor: str, now: float, ttl: float = LEASE_TTL) -> bool:
    """Atomically claim `task` for REVIEW — one row, one winner, same shape as
    `Live.acquire`. Re-claiming your own review renews it."""
    try:
        with live.db:
            live.db.execute("DELETE FROM reviews WHERE task = ? AND expires <= ?", (task, now))
            cursor = live.db.execute(
                "INSERT OR IGNORE INTO reviews (task, actor, acquired, expires)"
                " VALUES (?, ?, ?, ?)",
                (task, actor, now, now + ttl),
            )
            if cursor.rowcount != 1:
                held: list[Row] = live.db.execute(
                    "SELECT actor FROM reviews WHERE task = ?", (task,)
                ).fetchall()
                if not held or str(held[0][0]) != actor:
                    return False
                live.db.execute("UPDATE reviews SET expires = ? WHERE task = ?", (now + ttl, task))
    except sqlite3.Error as err:
        raise TaskopsError(f"live store: cannot claim review of {task}: {err}") from err
    return True


def reviewer(live: Live, task: str, now: float) -> str | None:
    rows = live.db.execute(
        "SELECT actor FROM reviews WHERE task = ? AND expires > ?", (task, now)
    ).fetchall()
    return str(rows[0][0]) if rows else None


class Held(NamedTuple):
    """A live review lease, as much of it as a reader outside this store needs:
    who is checking, and WHEN THAT REVIEW began. The second half is not a
    detail — a screen counting a review lease down from the work lease's
    `acquired` can only state a floor, and reads 0 while the lease is provably
    still live (`ui/src/components/monitor/LiveLeases.tsx::checked`)."""

    actor: str
    acquired: float


def held(live: Live, now: float) -> dict[str, Held]:
    """task -> the live review lease. One query; `reviewing()` is its actor half."""
    rows = live.db.execute(
        "SELECT task, actor, acquired FROM reviews WHERE expires > ?", (now,)
    ).fetchall()
    return {str(r[0]): Held(str(r[1]), float(r[2])) for r in rows}


def reviewing(live: Live, now: float) -> dict[str, str]:
    """task -> actor, for every LIVE review lease."""
    return {task: lease.actor for task, lease in held(live, now).items()}


def drop(live: Live, task: str, actor: str) -> bool:
    """Only the holder — same contract as `Live.release`."""
    try:
        with live.db:
            cursor = live.db.execute(
                "DELETE FROM reviews WHERE task = ? AND actor = ?", (task, actor)
            )
            return cursor.rowcount == 1
    except sqlite3.Error as err:
        raise TaskopsError(f"live store: cannot drop review of {task}: {err}") from err
