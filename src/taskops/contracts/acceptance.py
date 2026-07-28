"""Acceptance criteria on a card, in EARS, and the evidence that closes them.

EARS ("WHEN <trigger> THE SYSTEM SHALL <response>") is here because a criterion written that
way maps almost one-to-one onto a test case: the trigger is the arrange, the response is the
assert. A card whose "done" is prose leaves every reader — the worker, the verifier, the human
at 9am — to invent their own definition, and they invent different ones.

Not a column. Criteria are EVENTS, exactly like the context facts next door, so they replicate
through `git pull`, are content-hashed against a double import, and keep their own history: a
card whose criteria were tightened mid-flight can still show what it was originally accepted
against. It is also why a card written before this existed still works everywhere — no
criteria is an empty list, never a missing field.
"""

from __future__ import annotations

from typing import TypedDict

__all__ = ["ACCEPTANCE_KIND", "KEYWORDS", "SHALL", "AcceptanceCheck"]

ACCEPTANCE_KIND = "acceptance"
"""One event kind, body `{"criteria": [...]}`. The LATEST such event on a card wins, because
rewriting the criteria is a statement about the card now, not an amendment to be merged."""

KEYWORDS = ("when", "while", "where", "if", "the")
"""How an EARS line may open. `the` covers the ubiquitous form ("THE SYSTEM SHALL …"), which
has no trigger clause at all and is the right shape for an invariant-style criterion."""

SHALL = "shall"
"""The one word every EARS pattern shares. Its absence is the strongest signal that a line is
prose — and still only a WARNING, never a refusal. A criterion rejected over grammar is a
criterion nobody writes down, which is strictly worse than a badly worded one."""


class AcceptanceCheck(TypedDict):
    """What a caller gets back: the criteria as stored, and what looked off about them."""

    criteria: list[str]
    warnings: list[str]
    """One line per criterion that does not read as EARS, naming the criterion. Advisory: the
    criteria in this same result were stored regardless."""
