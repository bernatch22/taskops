"""The tasks table."""

from __future__ import annotations

import sqlite3

from .._errors import BadRequest, NoSuchTask
from .._types import EDITABLE_FIELDS, Status
from ..contracts import Task
from ._rows import dumps, to_task

__all__ = ["TaskTable"]

_COLUMNS = ("id", "title", "spec", "status", "priority", "parent", "labels",
            "files", "created_by", "assignee", "reviewer", "created", "updated")


def _values(task: Task) -> tuple[object, ...]:
    """A task in `_COLUMNS` order. One function, so the two orders cannot drift."""
    return (task["id"], task["title"], task["spec"], task["status"],
            task["priority"], task["parent"], dumps(task["labels"]),
            dumps(task["files"]), task["created_by"], task["assignee"], task["reviewer"],
            task["created"], task["updated"])


class TaskTable:
    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db

    def insert(self, task: Task) -> None:
        """Fails LOUDLY on a duplicate id rather than replacing.

        Task ids are random, so a collision is either a 1-in-16-million accident or
        a caller re-sending a plan — and silently overwriting the second case would
        destroy a task somebody is already working on.
        """
        marks = ", ".join("?" * len(_COLUMNS))
        self.db.execute(f"INSERT INTO tasks ({', '.join(_COLUMNS)}) "
                        f"VALUES ({marks})", _values(task))

    def upsert(self, task: Task) -> None:
        """Last-writer-wins by `updated`, for the sync path only.

        Two machines editing one task is rare and the log records both edits, so
        the loser is recoverable. Refusing the import instead would make a
        `git pull` fail on something git itself merged cleanly.
        """
        if self.get(task["id"]) is None:
            self.insert(task)
            return
        self.db.execute(
            "UPDATE tasks SET title=?, spec=?, status=?, priority=?, parent=?, "
            "labels=?, files=?, updated=? WHERE id=? AND updated<=?",
            (task["title"], task["spec"], task["status"], task["priority"],
             task["parent"], dumps(task["labels"]), dumps(task["files"]),
             task["updated"], task["id"], task["updated"]))

    def get(self, task_id: str) -> Task | None:
        row = self.db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return to_task(row) if row else None

    def need(self, task_id: str) -> Task:
        """The read that refuses to return None — most callers cannot proceed."""
        found = self.get(task_id)
        if found is None:
            raise NoSuchTask.named(task_id)
        return found

    def set_assignee(self, task_id: str, actor: str, *, when: float) -> None:
        """Point a card at somebody, or back at the pool with "".

        Its own method rather than a general `update`: assignment changes who the SCHEDULER will
        offer the card to, which is a different kind of write from editing a title, and the two want
        different events in the log.
        """
        self.db.execute("UPDATE tasks SET assignee=?, updated=? WHERE id=?",
                        (actor, when, task_id))

    def set_field(self, task_id: str, field: str, value: object, *, when: float) -> None:
        """Rewrite ONE editable column — a title, a spec, a priority.

        The column name is interpolated, so it is checked against `EDITABLE_FIELDS` first and
        nowhere else: a whitelist at the only place that builds the SQL is the difference
        between a typo and an injection, and every caller above reaches this one door.
        """
        if field not in EDITABLE_FIELDS:
            raise BadRequest(f"`{field}` is not editable — use one of "
                             f"{', '.join(EDITABLE_FIELDS)}")
        self.db.execute(f"UPDATE tasks SET {field}=?, updated=? WHERE id=?",
                        (value, when, task_id))

    def set_status(self, task_id: str, status: Status, *, when: float) -> None:
        self.db.execute("UPDATE tasks SET status=?, updated=? WHERE id=?",
                        (status, when, task_id))

    def all(self) -> list[Task]:
        """Every task, most urgent first. The board's one read."""
        rows = self.db.execute("SELECT * FROM tasks "
                               "ORDER BY priority, created").fetchall()
        return [to_task(row) for row in rows]

    def with_status(self, statuses: tuple[str, ...]) -> list[Task]:
        marks = ", ".join("?" * len(statuses))
        rows = self.db.execute(f"SELECT * FROM tasks WHERE status IN ({marks}) "
                               f"ORDER BY priority, created", statuses).fetchall()
        return [to_task(row) for row in rows]

    def children(self, parent: str) -> list[Task]:
        rows = self.db.execute("SELECT * FROM tasks WHERE parent=? "
                               "ORDER BY priority, created", (parent,)).fetchall()
        return [to_task(row) for row in rows]

    def search(self, text: str, *, limit: int = 20) -> list[Task]:
        """Substring over title and spec, case-insensitive.

        Not FTS5: it is a compile-time option missing from some distro pythons, and
        a task list is thousands of rows rather than millions. A LIKE scan that
        always works beats an index absent on a teammate's machine.
        """
        like = f"%{text.lower()}%"
        rows = self.db.execute(
            "SELECT * FROM tasks WHERE LOWER(title) LIKE ? OR LOWER(spec) LIKE ? "
            "ORDER BY priority, created LIMIT ?", (like, like, limit)).fetchall()
        return [to_task(row) for row in rows]
