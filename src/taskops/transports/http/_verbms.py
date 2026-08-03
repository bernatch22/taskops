"""The rpc rows a CHAPTER needs — its own table, merged into `VERBS`.

`_verbs` states why this file exists better than a new sentence would: that table hit its budget
"with a verb still to add, and a list nobody can append to without deleting something has stopped
being a list of what the surface is". This is eight more, so they get a table of their own — one
per subject, appended to rather than fought over.

**Every move routes.** A milestone is the only thing on a board that ENDS, so a move applied in a
clone would be a chapter that closed on one machine and stayed open on every other — the exact
split brain the routing layer exists to prevent, and one nobody would notice until a worker was
still reading rules from a chapter its board had already shipped.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ...contracts.milestone import Milestone
from ...usecases import milestone as ms
from ._verbargs import strings as _strings

__all__ = ["MILESTONE_VERBS"]

MILESTONE_VERBS: dict[str, Callable[[Path, dict[str, Any]], Any]] = {
    # A chapter is the only thing on a board that ENDS, so every one of its moves routes: applied
    # locally it would be a milestone that closed on one machine and stayed open everywhere else.
    "milestone_create": lambda root, a: _wrapped(ms.open_chapter(
        root, str(a.get("text", "")), horizon=str(a.get("horizon", "")),
        planned=bool(a.get("planned")), actor=str(a.get("actor", "")))),
    "milestone_update": lambda root, a: _wrapped(ms.edit(
        root, str(a.get("milestone", "")), text=str(a.get("text", "")),
        horizon=str(a.get("horizon", "")), actor=str(a.get("actor", "")))),
    "milestone_move": lambda root, a: _wrapped(_moved(root, a)),
    "milestone_review": lambda root, a: _wrapped(ms.hand_over(
        root, str(a.get("milestone", "")), note=str(a.get("m", "")),
        actor=str(a.get("actor", "")))),
    "milestone_done": lambda root, a: _wrapped(ms.verify(
        root, str(a.get("milestone", "")), carry=tuple(_strings(a, "carry")),
        into=str(a.get("into", "")), actor=str(a.get("actor", "")))),
    "milestone_cancel": lambda root, a: _wrapped(ms.abandon(
        root, str(a.get("milestone", "")), note=str(a.get("m", "")),
        actor=str(a.get("actor", "")))),
    "milestone_list": lambda root, _a: ms.listing(root),
    "milestone_show": lambda root, a: _wrapped(ms.chapter(root, str(a.get("milestone", "")))),
}


def _wrapped(found: Milestone) -> dict[str, Any]:
    """One milestone, under a key. Every verb answers an OBJECT — the client decoder returns `{}`
    for anything else, silently — and a `Milestone` happens to be one already, but naming the key
    is what stops the next reader having to know that."""
    return {"milestone": found}


def _moved(root: Path, a: dict[str, Any]) -> Milestone:
    """`start` and the reject-bounce are ONE op: the resulting state is the same, and a second name
    would be a second thing to keep in step. Which of the two it is depends only on where the
    chapter was — so the machine decides and this does not, and the presence of a message tells
    them apart, because a rejection without one is refused anyway.
    """
    wanted, note = str(a.get("milestone", "")), str(a.get("m", ""))
    actor = str(a.get("actor", ""))
    return (ms.send_back(root, wanted, note=note, actor=actor) if note
            else ms.start(root, wanted, actor=actor))
