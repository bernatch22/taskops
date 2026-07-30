"""`reviewer: peer` — the rule that nobody signs off on work their own agents produced.

Its own module because `_review` was at its budget and this is a distinct question. Every other
guard there asks about the CARD (does it have a commit, are its children closed, did the actor
who opened the review try to close it); this one asks about the PEOPLE, and answering it needs
identity parsing that the rest of that module has no use for.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._errors import BadRequest
from .._types import PEER
from .identity import parse

if TYPE_CHECKING:                          # pragma: no cover - typing only
    from .machine import Facts

__all__ = ["reviewer_is_a_peer"]


def reviewer_is_a_peer(facts: Facts) -> str | None:
    """`reviewer: peer` — nobody signs off on work their OWN agents produced.

    The hole this closes was found in a live two-developer run and it is the same bug that was
    called critical once already, arriving through a different door. `_handed_on` compares
    ACTOR IDS, so `dev:dev2` closing a card that `agent:dev2/w1` handed over is two different
    strings and passes — while being, in every sense that matters, the author closing their own
    work. It happened to two cards, WHILE independent verifiers were still running on them;
    both verifiers had to write their verdict as a comment because `done` is terminal.

    So the comparison is by DEV. An `agent:dev2/w1` and a `dev:dev2` are one person with two
    hands.

    It is OPT-IN, per project, because the default has to keep a solo developer working: with
    nobody else on the board, refusing every close would make the tool unusable for the most
    common way it is first tried. A team states it once:

        taskops context decision "reviewer: peer"

    and from then on every card is created with `reviewer: peer` and needs somebody from
    another dev to close it.
    """
    if facts.reviewer != PEER:
        return None
    mine = _dev_of(facts.actor)
    author = _dev_of(facts.entered_review_by) or _dev_of(facts.task["assignee"])
    if not mine or not author or mine != author:
        return None
    author_id = facts.entered_review_by or facts.task["assignee"] or f"an agent of {mine}"
    return (f"{facts.task['id']} is `reviewer: peer` and {author_id} handed it over — nobody "
            f"on {mine} closes work {mine} produced. Hand it to another developer's session, "
            f"or to a verifier they spawn.")


def _dev_of(actor: str) -> str:
    """The person behind an actor id, or "" for anything unparseable. Never raises: a guard
    that threw on a legacy id would refuse a close for a reason nobody could act on."""
    try:
        return parse(actor)["dev"] if actor else ""
    except BadRequest:
        return ""
