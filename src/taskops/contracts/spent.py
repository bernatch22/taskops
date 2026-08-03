"""Time, as this system is willing to claim it: a floor and a sitting, never an estimate.

Its own module because the board's contracts said so — the budget refused one more type in
`board.py`, and it was right that these are a different subject. A board's types describe what
EXISTS (a card, a column, an actor's counts); these describe what the log lets anybody infer about
attention, which is a weaker kind of statement and has to stay labelled as one.

`engine.timespent` is where the arithmetic and its one constant live.
"""

from __future__ import annotations

from typing import TypedDict

__all__ = ["Attended", "Stretch"]


class Attended(TypedDict):
    """One actor's time on one card: a LOWER BOUND, and `engine.timespent` argues why.

    `seconds` sums the gaps between that actor's consecutive events on that card, each gap capped, so
    it under-reports on purpose. Every surface drawing it has to SAY so — the alternative invents the
    one thing the log does not record, which is when somebody stopped.
    """

    task: str
    seconds: float
    events: int

class Stretch(TypedDict):
    """One SITTING of an actor's work: a run of their events with no gap past the cap.

    Several cards in one of these is the answer to "what were they doing at the same time" —
    alternating between them in one stretch of attention, rather than on the same calendar day,
    which says nothing. Cut on the same gap the time is capped at, because it is the same claim.
    """

    started: float
    ended: float
    tasks: list[str]
    """In the order they were FIRST touched: the order somebody opened them."""

    events: int
