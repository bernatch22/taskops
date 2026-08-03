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

    spent: list[Attended]
    """The cards of this sitting with the minutes spent on each INSIDE it, in the order they were
    first touched.

    Per sitting and not per period, which is the whole reason this field exists rather than a list of
    ids. A row drawn inside a group has to be checkable against that group's own header: the card
    totals were the period's, so a card with 32 minutes across the fortnight was drawn inside an
    eleven-minute stretch and read as thirty-two minutes of it. These partition the span exactly —
    no gap inside a sitting exceeds the cap, so nothing is lost to capping either.
    """

    events: int
