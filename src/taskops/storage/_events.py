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

    def newest_since(self, ts: float, *, limit: int) -> list[Event]:
        """The LAST `limit` events in a window, oldest first — what a history view reads.

        Not `since(...)[-limit:]`: `LIMIT` applies to the ascending scan, so that expression takes
        the OLDEST rows and then shows them as the newest. On a thirty-day window over a busy
        project it produced a timeline that was entirely correct and entirely the wrong end.

        Ordered DESC to pick the tail and reversed here, so callers still get the log's own order.
        """
        rows = self.db.execute("SELECT * FROM events WHERE ts > ? "
                               "ORDER BY ts DESC, seq DESC LIMIT ?", (ts, limit)).fetchall()
        return [to_event(row) for row in reversed(rows)]

    def after_seq(self, seq: int, *, limit: int = 200) -> list[Event]:
        """The studio's cursor read: strictly local order, no clock involved.

        A separate process cannot see the in-process event bus, so the live board
        polls this. Ordering by `ts` there would drop an event whose clock came
        from a machine running slightly behind.
        """
        return self.page_after(seq, limit=limit)[0]

    def page_after(self, seq: int, *, limit: int) -> tuple[list[Event], int]:
        """The same read, plus the seq of the LAST row scanned — the replication cursor.

        `Event` carries no `seq` on purpose: seq is this machine's local order, not the event's
        identity, and putting it in the contract would invite a puller to store another
        machine's numbering as if it were its own. So a page that ends mid-log has to hand its
        cursor back beside the events rather than inside them.

        Last SCANNED and not last returned, because a caller that filters the page (the HTTP
        exchange drops local-only kinds) would otherwise re-scan the dropped tail forever.
        """
        rows = self.db.execute(
            "SELECT * FROM events WHERE seq > ? ORDER BY seq LIMIT ?", (seq, limit)
        ).fetchall()
        return [to_event(row) for row in rows], int(rows[-1]["seq"]) if rows else seq

    def max_seq(self) -> int:
        row = self.db.execute("SELECT COALESCE(MAX(seq), 0) AS n FROM events").fetchone()
        return int(row["n"])

    def all(self) -> list[Event]:
        """Every event, log order. The reconcile's read — nothing hot-path calls this."""
        rows = self.db.execute("SELECT * FROM events ORDER BY ts, seq").fetchall()
        return [to_event(row) for row in rows]

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

    def stamps_by_task(self) -> list[tuple[str, str, str, float]]:
        """Every event as `(task, actor, kind, ts)`, ordered by task. ONE query for a whole board.

        Same bargain `count_by_task` makes: the board needs a per-card number folded from every
        event, and asking per task is what turns a page that is fine at fifty cards into one that
        stalls at five hundred. Four columns and not whole events, because the fold that reads this
        only needs who, what and when — pulling bodies would be reading the log to throw it away.

        A flat list and not a dict: grouping is the fold's job, and doing it here made this module
        the second place that knows how the number is built. The budget said so.
        """
        rows = self.db.execute(
            "SELECT task, actor, kind, ts FROM events ORDER BY task, ts").fetchall()
        return [(str(r["task"]), str(r["actor"]), str(r["kind"]), float(r["ts"])) for r in rows]

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
