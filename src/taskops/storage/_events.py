"""The events table — the append-only log every projection is derived from.

Writes are `INSERT OR IGNORE` on a content-hash id, which is what makes the whole
replication story work: the same event can arrive from a `git pull` and from the
relay, and the second one is a no-op instead of a duplicate.
"""

from __future__ import annotations

import sqlite3

from ..contracts import Event
from ._rows import dumps, to_event

__all__ = ["EventTable"]


class EventTable:
    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db

    def append(self, event: Event, *, exported: bool = False) -> bool:
        """True if this event is new here. False means we already had it.

        `seq` is assigned by SQLite's own rowid sequence via a subquery rather
        than AUTOINCREMENT on the primary key, because the primary key has to stay
        the content hash — so local ordering and global identity are two columns
        instead of one compromise.
        """
        cursor = self.db.execute(
            "INSERT OR IGNORE INTO events (id, seq, task, actor, kind, body, ts, "
            "exported) VALUES (?, (SELECT COALESCE(MAX(seq), 0) + 1 FROM events), "
            "?, ?, ?, ?, ?, ?)",
            (event["id"], event["task"], event["actor"], event["kind"],
             dumps(event["body"]), event["ts"], int(exported)))
        return cursor.rowcount == 1

    def of_task(self, task_id: str, *, kinds: tuple[str, ...] = ()) -> list[Event]:
        """One task's history, oldest first."""
        sql = "SELECT * FROM events WHERE task=?"
        params: tuple[object, ...] = (task_id,)
        if kinds:
            sql += f" AND kind IN ({', '.join('?' * len(kinds))})"
            params += kinds
        rows = self.db.execute(sql + " ORDER BY ts, seq", params).fetchall()
        return [to_event(row) for row in rows]

    def since(self, ts: float, *, limit: int = 500) -> list[Event]:
        """Everything after a moment — what a standup and the live feed both read."""
        rows = self.db.execute("SELECT * FROM events WHERE ts > ? "
                               "ORDER BY ts, seq LIMIT ?", (ts, limit)).fetchall()
        return [to_event(row) for row in rows]

    def after_seq(self, seq: int, *, limit: int = 200) -> list[Event]:
        """The studio's cursor read: strictly local order, no clock involved.

        A separate process cannot see the in-process event bus, so the live board
        polls this. Ordering by `ts` there would drop an event whose clock came
        from a machine running slightly behind.
        """
        rows = self.db.execute(
            "SELECT * FROM events WHERE seq > ? ORDER BY seq LIMIT ?", (seq, limit)
        ).fetchall()
        return [to_event(row) for row in rows]

    def max_seq(self) -> int:
        row = self.db.execute("SELECT COALESCE(MAX(seq), 0) AS n FROM events").fetchone()
        return int(row["n"])

    def unexported(self, *, limit: int = 1000) -> list[Event]:
        """What the committed log has not seen yet, oldest first."""
        rows = self.db.execute("SELECT * FROM events WHERE exported = 0 "
                               "ORDER BY seq LIMIT ?", (limit,)).fetchall()
        return [to_event(row) for row in rows]

    def mark_exported(self, ids: list[str]) -> None:
        marks = ", ".join("?" * len(ids))
        self.db.execute(f"UPDATE events SET exported = 1 WHERE id IN ({marks})",
                        tuple(ids))

    def count_by_task(self, kind: str) -> dict[str, int]:
        """How many events of one kind each task has. ONE query for a whole board.

        A board needs a commit count per card, and asking per task is what turns a
        page that was fine at fifty tasks into one that stalls at five hundred.
        """
        rows = self.db.execute("SELECT task, COUNT(*) AS n FROM events "
                               "WHERE kind=? GROUP BY task", (kind,)).fetchall()
        return {str(row["task"]): int(row["n"]) for row in rows}

    def latest_by_task(self, kind: str) -> dict[str, Event]:
        """The most recent event of one kind, per task — the fleet view's read.

        `MAX(seq)` in a subquery rather than sorting in Python: this runs on every
        board refresh, and `activity` is by far the largest kind in the table.
        """
        rows = self.db.execute(
            "SELECT * FROM events WHERE kind=? AND seq IN ("
            "  SELECT MAX(seq) FROM events WHERE kind=? GROUP BY task)",
            (kind, kind)).fetchall()
        return {str(row["task"]): to_event(row) for row in rows}
