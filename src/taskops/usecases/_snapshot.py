"""A card as another machine has to receive it.

Split from `plan` on its budget, and the seam is real: that module DECIDES a card — its chapter,
its reviewer, its place in a tree — and this only says what has to cross for somebody else to
rebuild it. It is read by `engine.replay` on the other side, which is why it lives away from the
code that mints ids: the two are edited by different questions.
"""

from __future__ import annotations

from typing import Any

from ..contracts import Task

__all__ = ["snapshot"]


def snapshot(task: Task) -> dict[str, Any]:
    """Everything needed to recreate this task elsewhere. `id` and `created_by` are already on the
    event, so repeating them would be two places to keep in step."""
    return {"title": task["title"], "spec": task["spec"], "priority": task["priority"],
            "parent": task["parent"], "labels": task["labels"], "files": task["files"],
            "assignee": task["assignee"], "reviewer": task["reviewer"],
            "milestone": task["milestone"]}
