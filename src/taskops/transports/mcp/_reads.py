"""Handlers that only QUERY: read a task, search, or render a projection.

Split from `_handlers` because there are seven tools and one file of them stopped being readable. The
seam is what a handler DOES: these answer questions and change nothing, so they are safe to call twice and their only
real decisions are about SHAPE — `ask` serves two forms behind one tool, and `report` four.
"""

from __future__ import annotations

from typing import Any

from ...render import (
    render_board,
    render_day,
    render_search,
    render_standup,
    render_view,
)
from ...usecases import (
    ask,
    board,
    day,
    search,
    standup,
)
from . import arguments as arg

__all__ = ["ask_", "report_"]


def ask_(args: dict[str, Any]) -> str:
    """`task` or `query`, and saying so when neither came.

    Two shapes behind one tool: an agent either knows which task it means or it does not,
    and making that two tools would have it choose wrong half the time.
    """
    if wanted := arg.optional(args, "task"):
        return render_view(ask(arg.repo(args), wanted,
                               actor=arg.optional(args, "actor")))
    if query := arg.optional(args, "query"):
        return render_search(search(arg.repo(args), query), query)
    raise arg.Missing("pass `task` to read one, or `query` to search")


def report_(args: dict[str, Any]) -> str:
    """Three kinds, and an unknown one is REFUSED rather than quietly given a board.

    `fleet` and `burndown` used to be answerable here. Falling through to the board would
    hand an agent that asked for one of them a report about something else and no way to
    tell — so the removal is stated, with what to ask for instead.
    """
    kind = arg.optional(args, "kind") or "board"
    where = arg.repo(args)
    if kind == "standup":
        return render_standup(standup(where, since=arg.optional(args, "since") or "24h",
                                      actor=arg.optional(args, "actor")))
    if kind == "day":
        return render_day(day(where, arg.optional(args, "date") or "today"))
    if kind != "board":
        raise arg.Missing(f"`{kind}` is not a report — ask for `board`, `standup` or `day`")
    return render_board(board(where))


