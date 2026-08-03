"""What a fact must BE before anything opens a store — the four refusals `state` owes its caller.

Split out of `context.py` on its budget, and the seam is worth naming: that module records a fact
and routes it, this one decides whether it is a fact at all. Every check here is a pure function of
the arguments, which is what makes the vocabulary testable without a board.

They run in this order and the order matters: shape, then WHO, then ownership. An agent stating an
unowned objective is refused for who it is — a message about ownership would send it to fix the
wrong half, and it would fix it, and it would still be refused.
"""

from __future__ import annotations

from .._errors import BadRequest
from ..contracts.context import LEVELS, SORTS
from .policy import refuse_if_policy

__all__ = ["refuse_the_shape", "refuse_an_ownerless_objective"]


def refuse_an_ownerless_objective(owner: str) -> None:
    """An objective is ALWAYS somebody's. The project's north is a milestone now.

    Refused rather than accepted-and-hidden, which is what happened first: an unowned objective
    is filed under nobody, so it lands in no dev's page and in no card's slice — stated, stored,
    and read by nothing. Old boards have them and the renderer marks those `project`; what this
    stops is writing another one.
    """
    if not owner:
        raise BadRequest("an objective belongs to one person — the project's north is a MILESTONE "
                         "now, so state it as yours (`taskops me objective \"…\"`, or "
                         "`taskops_context state=objective`), or open a chapter with "
                         "`taskops milestone new`")


def refuse_the_shape(sort: str, text: str, level: str) -> None:
    """What a fact must be before anything opens a store. Its own function so `state` reads as the
    write it is — and because these four are the vocabulary, which belongs in one place."""
    if sort not in SORTS:
        raise BadRequest(f"`{sort}` is not a context fact — expected {', '.join(SORTS)}")
    if not text.strip():
        raise BadRequest(f"an {sort} needs text — a fact with no statement states nothing")
    if level not in LEVELS:
        raise BadRequest(f"`{level}` is not a level — expected {', '.join(LEVELS)}")
    if sort == "note" and level == "project":
        raise BadRequest("a note is always a chapter's: if it is permanent it is a `rule` or a "
                         "`decision`, and a note that outlived its chapter is the scratchpad that "
                         "made a slice grow forever")
    refuse_if_policy(text)
