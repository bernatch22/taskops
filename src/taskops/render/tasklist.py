"""The task list as ONE line per card — what `taskops tasks` prints.

`render.board` answers "what is the state of the work": eight columns, always all of them,
because a missing column reads as a bug. This answers a different question — "what is on
my list" — so the columns collapse into a single ordered list. A reader scanning for an id
does not want a heading and a table rule between every second row.

Closed cards are left out here, and only here. `done` and `cancelled` accumulate for the
life of a project, so a list that included them would grow without bound and be read only
as far as the first screen; the board still shows them, counted, which is where "what is
finished" belongs.
"""

from __future__ import annotations

from .._types import OPEN_STATUSES
from ..contracts import Board, Card
from ._text import STATUS_MARK, truncate

__all__ = ["render_tasklist"]


def render_tasklist(board: Board) -> str:
    """A line per open task, then one summary line.

    The summary is the same `ready` count the board leads with: it is the only number that
    says whether adding another agent would help, and a person reading their list is
    exactly the person deciding that.
    """
    rows = [_line(card, column["status"])
            for column in board["columns"] if column["status"] in OPEN_STATUSES
            for card in column["cards"]]
    if not rows:
        return f"no open tasks ({board['total']} in total)"
    return "\n".join([*rows, "", f"{len(rows)} open, {board['ready']} ready"])


def _line(card: Card, status: str) -> str:
    """`◐ tk-4f2a9c  claimed      Regroup the CLI              ← agent:berna/v21`

    Padded rather than tabulated: a markdown table costs three characters of framing per
    column and this view exists to be compact. The holder is suffixed with an arrow instead
    of a column of its own, because most rows have none and a mostly-empty column is a
    column of noise.
    """
    who = card["lease"]["actor"] if card["lease"] else ""
    return (f"{STATUS_MARK.get(status, '?')} {card['task']['id']}  {status:<12}"
            f"{truncate(card['task']['title'], 52)}" + (f"  ← {who}" if who else ""))
