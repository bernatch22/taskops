"""The row, the cap and the summary of `taskops tasks`. Pure, like the rest of `render/`.

Split out of `tasklist.py` for the file budget, and the seam is the honest one: that module
decides WHICH cards a reader is asking for, this one decides what one of them looks like on
a line and how a long list ends.
"""

from __future__ import annotations

from .._types import OPEN_STATUSES
from ..contracts import Board, Card
from ._text import STATUS_MARK, ago, truncate

__all__ = ["CAP", "lines", "capped", "summary"]

CAP = 10
"""How many rows of one group get printed before the rest become a count.

Closed cards accumulate for the life of a project, so an uncapped list would be read only
as far as the first screen anyway — and a reader who scrolls past forty finished cards to
reach the summary stops opening the command. Ten is a screen; `+N more` says the rest are
there, which is the part an empty tail would not.
"""


def lines(board: Board, statuses: frozenset[str], *, dated: bool = False) -> list[str]:
    """One line per card in `statuses`, newest-updated first when `dated`.

    Open cards keep the board's own order (priority, as the columns were built), because a
    list you are about to pick from is ordered by what to do next. Closed cards have no next,
    so they are ordered by when they stopped moving — which is what "what was worked on" asks.
    """
    cards = [(card, column["status"]) for column in board["columns"]
             if column["status"] in statuses for card in column["cards"]]
    if dated:
        cards.sort(key=lambda pair: pair[0]["task"]["updated"], reverse=True)
    return [_line(card, status, dated=dated) for card, status in cards]


def _line(card: Card, status: str, *, dated: bool = False) -> str:
    """`◐ tk-4f2a9c  claimed      Regroup the CLI              ← agent:berna/v21`

    Padded rather than tabulated: a markdown table costs three characters of framing per
    column and this view exists to be compact. The holder is suffixed with an arrow instead
    of a column of its own, because most rows have none and a mostly-empty column is a
    column of noise. A closed card has no holder and trades that suffix for its age, which
    is the only thing left that distinguishes yesterday's work from last quarter's.
    """
    who = card["lease"]["actor"] if card["lease"] else ""
    tail = f"  {ago(card['task']['updated'])}" if dated else (f"  ← {who}" if who else "")
    return (f"{STATUS_MARK.get(status, '?')} {card['task']['id']}  {status:<12}"
            f"{truncate(card['task']['title'], 52)}{tail}")


def capped(rows: list[str]) -> list[str]:
    """At most `CAP` rows, then a line saying how many were left out."""
    if len(rows) <= CAP:
        return list(rows)
    return [*rows[:CAP], f"+{len(rows) - CAP} more"]


def summary(board: Board, closed: int) -> str:
    """`3 open, 1 ready` — and the closed count whenever closed cards are on screen.

    The `ready` count is the one number that says whether adding another agent would help,
    and a person reading their list is exactly the person deciding that. The closed count
    appears only when closed rows do, so the line never describes something not shown.
    """
    count = sum(len(column["cards"]) for column in board["columns"]
                if column["status"] in OPEN_STATUSES)
    line = f"{count} open, {board['ready']} ready"
    return f"{line}, {closed} closed" if closed else line
