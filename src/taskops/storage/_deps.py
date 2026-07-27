"""The dependency edges. `task` must finish before `blocks` can start."""

from __future__ import annotations

import sqlite3

from .._types import CLOSED_STATUSES
from ..contracts import Dep

__all__ = ["DepTable"]


class DepTable:
    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db

    def add(self, task: str, blocks: str) -> None:
        """Idempotent: the same edge asserted twice is the same fact."""
        self.db.execute("INSERT OR IGNORE INTO deps (task, blocks) VALUES (?, ?)", (task, blocks))

    def remove(self, task: str, blocks: str) -> None:
        self.db.execute("DELETE FROM deps WHERE task=? AND blocks=?", (task, blocks))

    def all(self) -> list[Dep]:
        rows = self.db.execute("SELECT task, blocks FROM deps").fetchall()
        return [Dep(task=str(r["task"]), blocks=str(r["blocks"])) for r in rows]

    def blockers_of(self, task_id: str) -> list[str]:
        """Every id this task waits on, closed or not."""
        rows = self.db.execute("SELECT task FROM deps WHERE blocks=?", (task_id,)).fetchall()
        return [str(row["task"]) for row in rows]

    def dependents_of(self, task_id: str) -> list[str]:
        """Every id waiting on this one."""
        rows = self.db.execute("SELECT blocks FROM deps WHERE task=?", (task_id,)).fetchall()
        return [str(row["blocks"]) for row in rows]

    def open_blockers_of(self, task_id: str) -> list[str]:
        """The blockers that are still open — the ones that actually block.

        A JOIN rather than two queries and a filter in Python: this runs for every
        task in the ready-set computation, and the ready-set is recomputed after
        every write in the system.
        """
        marks = ", ".join("?" * len(CLOSED_STATUSES))
        closed = tuple(sorted(CLOSED_STATUSES))
        rows = self.db.execute(
            f"SELECT d.task FROM deps d JOIN tasks t ON t.id = d.task "
            f"WHERE d.blocks = ? AND t.status NOT IN ({marks})",
            (task_id, *closed),
        ).fetchall()
        return [str(row["task"]) for row in rows]

    def unblocked_by(self, task_id: str) -> list[str]:
        """Ids that have NO open blocker left once `task_id` is closed.

        Asked after a task closes, so `task_id` is already closed in the same
        transaction — which is why this needs no special case for it. The
        NOT EXISTS reads as the question: dependents with nothing open left.
        """
        marks = ", ".join("?" * len(CLOSED_STATUSES))
        closed = tuple(sorted(CLOSED_STATUSES))
        rows = self.db.execute(
            f"SELECT d.blocks AS id FROM deps d WHERE d.task = ? AND NOT EXISTS ("
            f"  SELECT 1 FROM deps o JOIN tasks t ON t.id = o.task"
            f"  WHERE o.blocks = d.blocks AND t.status NOT IN ({marks}))",
            (task_id, *closed),
        ).fetchall()
        return [str(row["id"]) for row in rows]
