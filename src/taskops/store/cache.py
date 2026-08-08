"""cache.sqlite — derived from the log, discardable, rebuildable.

Delete this file and the board is unchanged: `Stores.rebuild()` replays
`events.jsonl` into a fresh one. That is why leases live in a SEPARATE file
(`live.py`): in v1 they shared a database and clearing the cache silently
dropped every live claim.

`seq` is the rowid, so `MAX(seq)` is O(1) and the feed cursor is a plain
integer. v1 computed the next sequence with a scan on every insert — O(n²),
which is how a pull of a busy board came to take 33 seconds.

Every `sqlite3.Error` is converted here: no foreign exception leaves the
package (§5.2).
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Sequence
from pathlib import Path

from .._errors import TaskopsError
from ..core.types import Event

DDL = """
CREATE TABLE IF NOT EXISTS events (
    seq   INTEGER PRIMARY KEY AUTOINCREMENT,
    id    TEXT NOT NULL UNIQUE,
    task  TEXT NOT NULL,
    actor TEXT NOT NULL,
    kind  TEXT NOT NULL,
    body  TEXT NOT NULL,
    ts    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS events_task ON events(task, ts);
CREATE INDEX IF NOT EXISTS events_actor ON events(actor, ts);
"""

Row = tuple[Any, ...]


class Cache:
    """Append-only event index. Its only writer is `Stores`."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.db = sqlite3.connect(path, check_same_thread=False)
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=NORMAL")
            self.db.executescript(DDL)
            self.db.commit()
        except sqlite3.Error as err:
            raise TaskopsError(f"cannot open the cache at {path}: {err}") from err

    def add(self, events: Sequence[Event]) -> int:
        """INSERT OR IGNORE — content-addressed ids make a repeat a no-op."""
        rows = [
            (e["id"], e["task"], e["actor"], e["kind"], json.dumps(e["body"]), e["ts"])
            for e in events
        ]
        try:
            with self.db:
                self.db.executemany(
                    "INSERT OR IGNORE INTO events (id, task, actor, kind, body, ts)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    rows,
                )
        except sqlite3.Error as err:
            raise TaskopsError(f"cache: cannot index {len(rows)} events: {err}") from err
        return self.head()

    def head(self) -> int:
        rows = self._query("SELECT MAX(seq) FROM events")
        return int(rows[0][0] or 0) if rows else 0

    def count(self) -> int:
        return int(self._query("SELECT COUNT(*) FROM events")[0][0])

    def since(self, seq: int) -> list[tuple[int, Event]]:
        return self._events("WHERE seq > ? ORDER BY seq", (seq,))

    def page(self, before: int | None, limit: int) -> list[tuple[int, Event]]:
        """One page of the whole log, NEWEST FIRST, by keyset on `seq`.

        `before=None` is the newest page; otherwise the page is the rows
        strictly older than that cursor, and the caller passes back the `seq`
        of the last row it received.

        **Page by `seq`, never by `ts`, and do not "fix" this to a timestamp.**
        `seq` is `INTEGER PRIMARY KEY AUTOINCREMENT` — the rowid: unique,
        monotonic in arrival order, and a descending scan of it needs no index.
        `ts` is a float wall clock that ties constantly here (a plan of nine
        writes nine events inside one millisecond), and a cursor that ties at a
        page boundary either drops the rows sharing the boundary instant or
        serves them twice. `OFFSET` has the same defect for a different reason:
        the log grows under the reader, so every append shifts every offset.
        """
        if before is None:
            return self._events("ORDER BY seq DESC LIMIT ?", (limit,))
        return self._events("WHERE seq < ? ORDER BY seq DESC LIMIT ?", (before, limit))

    def by_task(self, task: str) -> list[Event]:
        """A card's thread, in ARRIVAL order.

        `seq`, not `ts`: two events written in the same second (or by a machine
        whose clock drifted) must still read in the order they reached the
        board. `replay` is the one that sorts by `(ts, id)`, because merging two
        histories is a different question from showing one.
        """
        return [e for _, e in self._events("WHERE task = ? ORDER BY seq", (task,))]

    def by_actor(self, actor: str, since_ts: float, until_ts: float) -> list[Event]:
        sql = "WHERE actor = ? AND ts >= ? AND ts < ? ORDER BY ts"
        return [e for _, e in self._events(sql, (actor, since_ts, until_ts))]

    def window(self, since_ts: float, until_ts: float) -> list[Event]:
        sql = "WHERE ts >= ? AND ts < ? ORDER BY ts"
        return [e for _, e in self._events(sql, (since_ts, until_ts))]

    def close(self) -> None:
        self.db.close()

    def _events(self, tail: str, args: Row) -> list[tuple[int, Event]]:
        sql = f"SELECT seq, id, task, actor, kind, body, ts FROM events {tail}"
        out: list[tuple[int, Event]] = []
        for seq, ident, task, actor, kind, body, ts in self._query(sql, args):
            out.append(
                (
                    int(seq),
                    Event(
                        id=str(ident),
                        task=str(task),
                        actor=str(actor),
                        kind=str(kind),
                        body=json.loads(str(body)),
                        ts=float(ts),
                    ),
                )
            )
        return out

    def _query(self, sql: str, args: Row = ()) -> list[Row]:
        try:
            rows: list[Row] = self.db.execute(sql, args).fetchall()
        except sqlite3.Error as err:
            raise TaskopsError(f"cache: {err}") from err
        return rows
