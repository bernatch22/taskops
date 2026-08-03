"""`taskops_milestone` — the chapter, and the one verb an agent may not finish.

Its own module like `_context`, and for the same reason: a tool whose shape carries an argument.
The argument here is about WHO. Creating a chapter is planning, starting it is beginning, working
under it is working, and saying it is finished is REPORTING — all four are an agent's job. Saying
it is reached is verifying, and that is not. `engine.milestones` refuses it, so the refusal holds
for every transport rather than for whichever one remembered.

**A bare call answers with every ACTIVE chapter.** Several are active on any real board, and the
orchestrator is the only reader that chooses between them — it plans into one and dispatches from
one, and it cannot do either blind. `milestone=<id>` answers with that chapter's cards too, which
is what makes "how do I reach its cards" one call instead of two.
"""

from __future__ import annotations

from typing import Any

from ...render.milestones import render_chapter, render_chapters
from ...usecases import milestone as ms
from ...usecases._contextviews import chapters
from ...usecases._project import project
from . import arguments as arg

__all__ = ["milestone_"]


def milestone_(args: dict[str, Any]) -> str:
    """Read the chapters, or move one. Every branch is one call to the use case and one render.

    The moves are checked in the order a session reaches for them, and the READ is last for the
    same reason `context_` puts it last: everything else says which shape was asked for, and what
    is left over is "show me".
    """
    where, who = arg.repo(args), arg.optional(args, "actor")
    if text := arg.optional(args, "create"):
        return _said(ms.open_chapter(where, text, horizon=arg.optional(args, "horizon"),
                                     planned=arg.flag(args, "planned"), actor=who), where)
    if wanted := arg.optional(args, "start"):
        return _said(ms.start(where, wanted, actor=who), where)
    if wanted := arg.optional(args, "update"):
        return _said(ms.edit(where, wanted, text=arg.optional(args, "text"),
                             horizon=arg.optional(args, "horizon"), actor=who), where)
    if wanted := arg.optional(args, "review"):
        return _said(ms.hand_over(where, wanted, note=arg.optional(args, "m"), actor=who), where)
    if wanted := arg.optional(args, "done"):
        return _said(ms.verify(where, wanted, carry=tuple(arg.csv(args, "carry")),
                               into=arg.optional(args, "into"), actor=who), where)
    if wanted := arg.optional(args, "reject"):
        return _said(ms.send_back(where, wanted, note=arg.optional(args, "m"), actor=who), where)
    if wanted := arg.optional(args, "cancel"):
        return _said(ms.abandon(where, wanted, note=arg.optional(args, "m"), actor=who), where)
    if wanted := arg.optional(args, "milestone"):
        return _one(where, wanted)
    return _all(where)


def _said(moved: Any, where: Any) -> str:
    """A chapter after a write: what it is now, plus its counts, because the next question after
    every one of these moves is "and how far along is it"."""
    with project(where) as store:
        return render_chapter(moved, chapters(store).counts.get(moved["id"], {}), cards=[])


def _one(where: Any, wanted: str) -> str:
    """ONE chapter with ITS CARDS — the answer to "how do I reach its cards" in one call.

    The cards come from the board rather than from the chapter, because a chapter does not own a
    list: a card names its milestone, so this is a filter and never a second thing to keep in step.
    """
    found = ms.chapter(where, wanted)
    with project(where) as store:
        cards = [dict(t) for t in store.tasks.all() if t["milestone"] == found["id"]]
        return render_chapter(found, chapters(store).counts.get(found["id"], {}), cards=cards)


def _all(where: Any) -> str:
    """Every active chapter with its counts, then what is planned. Reached ones are absent: this
    answers "what am I working on", and `milestone=<id>` is where a closed one is read on purpose.
    """
    with project(where) as store:
        found = chapters(store)
        return render_chapters(found.active, found.planned, found.counts)
