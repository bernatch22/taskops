"""One handler per tool: read the arguments, call the use case, pick a renderer.

Split from `dispatch` so that module stays what it is — a table plus the one place a typed failure
becomes an agent-readable sentence. Each function here is a few lines because it is allowed to be:
the use cases hold the behaviour and `render/` holds the words.
"""

from __future__ import annotations

from typing import Any

from ...render import (
    render_board,
    render_dispatch,
    render_fleet,
    render_next,
    render_plan,
    render_search,
    render_standup,
    render_update,
    render_view,
)
from ...usecases import (
    ask,
    board,
    dispatch,
    fleet,
    next_task,
    plan,
    search,
    standup,
    update,
)
from . import arguments as arg

__all__ = ["plan_", "next_", "update_", "ask_", "dispatch_", "report_"]


def plan_(args: dict[str, Any]) -> str:
    return render_plan(plan(arg.repo(args), arg.entries(args),
                            actor=arg.optional(args, "actor")))


def next_(args: dict[str, Any]) -> str:
    return render_next(next_task(arg.repo(args), actor=arg.optional(args, "actor"),
                                 session=arg.optional(args, "session"),
                                 labels=arg.csv(args, "labels"),
                                 task=arg.optional(args, "task")))


def update_(args: dict[str, Any]) -> str:
    return render_update(update(arg.repo(args), arg.text(args, "task"),
                                actor=arg.optional(args, "actor"),
                                status=arg.optional(args, "status"),
                                comment=arg.optional(args, "comment"),
                                mentions=arg.csv(args, "mentions"),
                                blocked_on=arg.optional(args, "blocked_on"),
                                no_code=arg.flag(args, "no_code")))


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


def dispatch_(args: dict[str, Any]) -> str:
    return render_dispatch(dispatch(arg.repo(args), tasks=arg.csv(args, "tasks"),
                                    count=arg.count(args), actor=arg.optional(args, "actor"),
                                    prefix=arg.optional(args, "prefix"),
                                    model=arg.optional(args, "model"),
                                    # `spawn` is NOT read, on purpose: this surface never starts a
                                    # process. See `DispatchParams` for why.
                                    dry_run=arg.flag(args, "dry_run")))


def report_(args: dict[str, Any]) -> str:
    kind = arg.optional(args, "kind") or "board"
    where = arg.repo(args)
    if kind == "standup":
        return render_standup(standup(where, since=arg.optional(args, "since") or "24h",
                                      actor=arg.optional(args, "actor")))
    if kind == "fleet":
        return render_fleet(fleet(where))
    if kind == "burndown":
        return ("burndown is not implemented yet — `board` shows the current state and "
                "`standup` shows a window")
    return render_board(board(where))


