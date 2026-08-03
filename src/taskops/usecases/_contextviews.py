"""Reading the standing facts — the three questions, and who is asking each one.

Split from the write verbs when the module filled up, and the line is not arbitrary: those two
carry guards, mint events and route to a server; these three are projections over a fold, and
the only decision any of them makes is **whose page this is**.

That decision is the whole feature. A fact with an owner belongs to one developer, so the same
store answers three different things depending on who asks — the overview (everybody's, for
deciding who to hand a card to), a person's own page, and the slice a worker is injected with.

They also resolve the CHAPTERS, which the slice cannot: `_contextslice` is pure, so it is handed
which milestones are active rather than opening a store to ask. `chapters` below is that lookup,
and it is one pass over the cards for the counts — a milestone is a todo-list only if "how far
along" is a number, and a number nobody computes is a claim.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from ..contracts import Task
from ..contracts.context import Fact
from ..contracts.slice import Chapters, ContextSlice
from ..engine import identity
from ..storage import Store
from ..storage.belonging import chapter_of, sole
from ..storage.context import facts
from ..storage.milestone import active, planned
from ._contextslice import for_task, in_force
from ._facts import entered_review_by
from ._moving import need
from ._project import locate, project
from ._routing import read_remote_first
from ._whose import dev_of

__all__ = ["show", "history", "context_for", "context_of", "chapters"]


def context_of(start: Path | str, wanted: str) -> ContextSlice:
    """What ONE chapter has settled — including a closed one, which is the point.

    A slice is what applies NOW, and a chapter that was reached applies to nothing: its facts left
    every slice the moment a person verified it. This is how they stay readable anyway, and it is
    deliberately an EXPLICIT act. "What did we decide while doing the importer" is a real question
    six months later; injecting the answer into every worker forever is how a context grows until
    compliance decays.
    """
    if (answer := read_remote_first(start, "context_of", {"milestone": wanted})) is not None:
        return cast("ContextSlice", answer)
    with project(start) as store:
        found = need(store, wanted)
        mine = [f for f in facts(store) if f["milestone"] == found["id"]]
        whole = in_force(mine, Chapters(active=[found], planned=[], counts=chapters(store).counts))
        whole["milestone"] = found
        whole["active"] = []
        return whole


def chapters(store: Store) -> Chapters:
    """Which milestones are being worked on, what is planned, and the cards of each.

    The counts come from ONE pass over the cards rather than a query per chapter: several are
    active, and a board with six of them would otherwise pay six scans to draw one strip.
    `cancelled` is counted like anything else here — the renderer decides what to show, because
    "3 of 9 done" and "3 of 9 done, 1 withdrawn" are two sentences and only one of them is a lie.
    """
    counts: dict[str, dict[str, int]] = {}
    only = sole(store)
    for task in store.tasks.all():
        # Legacy cards count in the board's only chapter rather than in a bucket beside it: the
        # answer is determined, so carrying it as an exception was the model contradicting itself.
        into = counts.setdefault(chapter_of(task, only), {})
        into[task["status"]] = into.get(task["status"], 0) + 1
        into["total"] = into.get("total", 0) + 1
    return Chapters(active=active(store), planned=planned(store), counts=counts)


def show(start: Path | str, *, actor: str = "", mine: bool = False) -> ContextSlice:
    """What is in force. The OVERVIEW by default; with `mine`, one person's own page.

    The overview shows everybody's objectives, because "who is on what" is what somebody
    deciding who to hand a card to needs, and it is the only view that answers it.
    """
    who = me(start, actor) if mine else ""
    if (answer := read_remote_first(start, "context_show", {"mine": who})) is not None:
        return cast("ContextSlice", answer)
    with project(start) as store:
        return in_force(facts(store), chapters(store), mine=who)


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
    """The slice one card gets: the project's facts plus its AUTHOR's, narrowed by subject.

    This is what a worker is handed instead of the book, and what `SessionStart` injects.

    The author is read HERE because it comes out of the event log and the slice is pure. On a
    card in review that is `entered_review_by` — the log's answer to "who handed this over" —
    and not `assignee`, which routing has overwritten with the reviewer by then.
    """
    if (answer := read_remote_first(start, "context_for", {"task": task_id})) is not None:
        return cast("ContextSlice", answer)
    with project(start) as store:
        task: Task = store.tasks.need(task_id)
        # Resolved here and not in the slice, which is pure: a card written before this board had
        # chapters otherwise reads a slice with no chapter in it — no goal, no rules — while the
        # board draws it inside one. The worker would be handed the emptier of two answers.
        whose: Task = {**task, "milestone": chapter_of(task, sole(store))}
        return for_task(facts(store), whose, chapters(store),
                        entered_review_by=entered_review_by(store, task_id))


def me(start: Path | str, actor: str) -> str:
    """This caller's DEV name — what `owner` is matched on."""
    return dev_of(identity.resolve(locate(start), actor)["id"])
