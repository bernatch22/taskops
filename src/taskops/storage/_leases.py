"""The leases table — where a hundred agents avoid each other.

The claim is ONE statement: `INSERT INTO leases` with `task` as the primary key,
preceded by a delete of whatever has expired. Two agents racing for one task are
two inserts on one key, and SQLite decides — no advisory lock, no lock file, no
retry loop. `Store` opens claims with BEGIN IMMEDIATE so the write lock is taken
before the expiry sweep reads, which is what stops the classic interleaving where
both sweeps delete the same dead lease and both then insert.

Every method takes `now` rather than reading a clock: expiry is the behaviour most
worth testing, and a test that has to sleep for fifteen minutes is a test nobody
runs.
"""

from __future__ import annotations

import sqlite3

from ..contracts import Lease
from ._rows import to_lease

__all__ = ["LeaseTable"]


class LeaseTable:
    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db

    def sweep(self, now: float) -> list[str]:
        """Drop expired leases; return the tasks that just came free.

        Returned rather than silently dropped because a task whose agent died has
        to be walked back out of `claimed` into `ready`, and only the caller knows
        how to write that transition.
        """
        rows = self.db.execute("SELECT task FROM leases WHERE expires <= ?", (now,)).fetchall()
        self.db.execute("DELETE FROM leases WHERE expires <= ?", (now,))
        return [str(row["task"]) for row in rows]

    def acquire(self, lease: Lease) -> bool:
        """True if the claim landed, False if somebody else holds it.

        `INSERT OR IGNORE` and then checking the row count is the atomic test —
        asking first and inserting second is the race this exists to avoid.
        """
        cursor = self.db.execute(
            "INSERT OR IGNORE INTO leases (task, actor, session, branch, acquired, "
            "expires) VALUES (?, ?, ?, ?, ?, ?)",
            (lease["task"], lease["actor"], lease["session"], lease["branch"],
             lease["acquired"], lease["expires"]))
        return cursor.rowcount == 1

    def get(self, task_id: str) -> Lease | None:
        row = self.db.execute("SELECT * FROM leases WHERE task=?", (task_id,)).fetchone()
        return to_lease(row) if row else None

    def held_by(self, task_id: str, actor: str, now: float) -> bool:
        """Does this actor hold a LIVE lease on this task.

        The precondition of every write an agent makes, so it checks expiry here
        rather than trusting a sweep to have run: a lease that lapsed one second
        ago is not a lease, whatever the table still says.
        """
        row = self.db.execute(
            "SELECT 1 FROM leases WHERE task=? AND actor=? AND expires > ?", (task_id, actor, now)
        ).fetchone()
        return row is not None

    def renew(self, *, task_id: str, actor: str, expires: float) -> bool:
        """Push the deadline out. Scoped to the holder, so a renewal cannot be
        used to steal a task by naming somebody else's."""
        cursor = self.db.execute(
            "UPDATE leases SET expires=? WHERE task=? AND actor=?", (expires, task_id, actor)
        )
        return cursor.rowcount == 1

    def set_branch(self, *, task_id: str, branch: str) -> None:
        self.db.execute("UPDATE leases SET branch=? WHERE task=?", (branch, task_id))

    def set_session(self, *, task_id: str, session: str) -> None:
        """Re-point a lease at the session now running it.

        A resumed Claude Code session gets a NEW id, so without this the board shows a
        live claim whose transcript path names a process that no longer exists.
        """
        self.db.execute("UPDATE leases SET session=? WHERE task=?", (session, task_id))

    def release(self, task_id: str) -> None:
        self.db.execute("DELETE FROM leases WHERE task=?", (task_id,))

    def live(self, now: float) -> list[Lease]:
        rows = self.db.execute(
            "SELECT * FROM leases WHERE expires > ? ORDER BY acquired", (now,)
        ).fetchall()
        return [to_lease(row) for row in rows]

    def of_actor(self, actor: str, now: float) -> list[Lease]:
        rows = self.db.execute(
            "SELECT * FROM leases WHERE actor=? AND expires > ? ORDER BY acquired", (actor, now)
        ).fetchall()
        return [to_lease(row) for row in rows]

    def of_session(self, session: str) -> list[Lease]:
        """What this Claude Code session is holding — the SessionStart read."""
        rows = self.db.execute(
            "SELECT * FROM leases WHERE session=? ORDER BY acquired", (session,)
        ).fetchall()
        return [to_lease(row) for row in rows]
