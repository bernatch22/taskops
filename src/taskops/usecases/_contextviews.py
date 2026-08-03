"""Reading the standing facts — the three questions, and who is asking each one.

Split from the write verbs when the module filled up, and the line is not arbitrary: those two
carry guards, mint events and route to a server; these three are projections over a fold, and
the only decision any of them makes is **whose page this is**.

That decision is the whole feature. A fact with an owner belongs to one developer, so the same
store answers three different things depending on who asks — the overview (everybody's, for
deciding who to hand a card to), a person's own page, and the slice a worker is injected with.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from ..contracts import Task
from ..contracts.context import ContextSlice, Fact
from ..engine import identity
from ..storage.context import facts
from ._contextslice import dev_of, for_task, in_force
from ._project import locate, project
from ._routing import read_remote_first

__all__ = ["show", "history", "context_for"]


def show(start: Path | str, *, actor: str = "", mine: bool = False) -> ContextSlice:
    """What is in force. The OVERVIEW by default; with `mine`, one person's own page.

    The overview shows everybody's objectives, because "who is on what" is what somebody
    deciding who to hand a card to needs, and it is the only view that answers it.
    """
    who = me(start, actor) if mine else ""
    if (answer := read_remote_first(start, "context_show", {"mine": who})) is not None:
        return cast("ContextSlice", answer)
    with project(start) as store:
        return in_force(facts(store), mine=who)


def history(start: Path | str) -> list[Fact]:
    """Everything ever stated, retired ones included and marked.

    NOT filtered by owner: the log is the record, and a record that hid what somebody else
    withdrew would be a record you cannot audit.
    """
    if (answer := read_remote_first(start, "context_history", {})) is not None:
        # A LIST inside an object: the wire decoder drops a bare array — see `_verbs`.
        return cast("list[Fact]", answer.get("facts", []))
    with project(start) as store:
        return facts(store, retired=True)


def context_for(start: Path | str, task_id: str) -> ContextSlice:
    """The slice one card gets: the project's facts plus its HOLDER's, narrowed by subject.

    This is what a worker is handed instead of the book, and what `SessionStart` injects.
    """
    if (answer := read_remote_first(start, "context_for", {"task": task_id})) is not None:
        return cast("ContextSlice", answer)
    with project(start) as store:
        task: Task = store.tasks.need(task_id)
        return for_task(facts(store), task)


def me(start: Path | str, actor: str) -> str:
    """This caller's DEV name — what `owner` is matched on."""
    return dev_of(identity.resolve(locate(start), actor)["id"])
