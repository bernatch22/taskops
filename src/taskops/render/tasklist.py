"""The task list as ONE line per card — what `taskops tasks` prints.

`render.board` answers "what is the state of the work": eight columns, always all of them,
because a missing column reads as a bug. This answers a different question — "what is on
my list" — so the columns collapse into a single ordered list. A reader scanning for an id
does not want a heading and a table rule between every second row.

Open cards lead, always: that is the question nine times out of ten, and closed ones
accumulate for the life of a project, so listing them by default would push the answer off
the screen. But a project whose cards are ALL closed used to print `no open tasks (6 in
total)` and nothing else — the same mistake the board fixed by never hiding a column. A
reader who cannot see the finished work cannot tell whether the tool lost it or whether the
project is done, so with nothing open the closed cards are what this prints, under a
heading that says which they are. `--all` shows both groups, `--status` picks exactly one.
"""

from __future__ import annotations

from .._types import CLOSED_STATUSES, OPEN_STATUSES
from ..contracts import Board
from ._tasklist import capped, lines, summary

__all__ = ["render_tasklist"]

Section = tuple[str, list[str]]


def render_tasklist(board: Board, *, show_all: bool = False,
                    status: str | None = None) -> str:
    """A line per task, then one summary line. See the module docstring for which tasks.

    `status` is trusted here — the caller validates it, because naming the legal values in
    a refusal is an edge's job and this renderer is reached by three of them.
    """
    if status is not None:
        rows = lines(board, frozenset({status}), dated=status in CLOSED_STATUSES)
        if not rows:
            return f"no {status} tasks ({board['total']} in total)"
        return _joined([(f"## {status} ({len(rows)})", rows)], board,
                       closed=len(rows) if status in CLOSED_STATUSES else 0)
    open_rows = lines(board, OPEN_STATUSES)
    closed_rows = lines(board, CLOSED_STATUSES, dated=True)
    if show_all:
        return _joined([("## open", open_rows), ("## closed", closed_rows)], board,
                       closed=len(closed_rows))
    if open_rows:
        return _joined([("", open_rows)], board, closed=0)
    if not closed_rows:
        return f"no open tasks ({board['total']} in total)"
    return _joined([("## nothing open — closed tasks, newest first", closed_rows)],
                   board, closed=len(closed_rows))


def _joined(sections: list[Section], board: Board, *, closed: int) -> str:
    """Headed groups, each capped, then the summary.

    The heading is "" for the ordinary open list, which is how that case keeps the shape it
    has always had: a heading over the only group on the page is a line that says nothing.
    """
    parts: list[str] = []
    for heading, rows in sections:
        if heading:
            parts += [heading, ""]
        parts += (capped(rows) if rows else ["_none_"]) + [""]
    return "\n".join([*parts, summary(board, closed)])
