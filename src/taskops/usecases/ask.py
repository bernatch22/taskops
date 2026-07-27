"""`taskops_ask` — reading. One task in full, or a search when there is no id.

Two shapes behind one tool because they are one intent with one missing piece: an
agent either knows which task it means or it does not, and making that two tools would
have it choose wrong half the time. With `task` it returns the whole context; with
`query` it returns candidates, and the agent asks again by id.
"""

from __future__ import annotations

from pathlib import Path

from .._errors import BadRequest
from ..contracts import Task, TaskView
from ._project import caller, heartbeat, project
from .view import view

__all__ = ["ask", "search"]


def ask(start: Path | str, task_id: str, *, actor: str = "") -> TaskView:
    """One task and everything around it."""
    if not task_id.strip():
        raise BadRequest("`task` is required — pass `query` instead to search")
    with project(start) as store:
        heartbeat(store, caller(store, actor)["id"])
        return view(store, task_id.strip())


def search(start: Path | str, query: str, *, limit: int = 20) -> list[Task]:
    """Tasks whose title or spec contains `query`.

    Comments are deliberately NOT searched. They are the largest text in the system
    and the least specific: a substring match over a conversation returns the task
    where somebody mentioned a word once, ranked identically to the task the word
    names. When this needs to be better it needs ranking, not a wider LIKE.
    """
    if not query.strip():
        raise BadRequest("`query` is required — a non-empty string")
    with project(start) as store:
        return store.tasks.search(query.strip(), limit=limit)
