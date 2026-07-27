"""One tool call -> the text the agent reads. A TABLE, never a chain of ifs.

Each handler is a few lines because it is allowed to be: the use cases hold the behaviour
and `render/` holds the words, so this layer only maps a name to one of each. That is the
whole reason the CLI, MCP and HTTP surfaces cannot drift — none of them is where a decision
lives.
"""

from __future__ import annotations

from typing import Any, Callable

from ..._errors import TaskopsError
from ...render import (
    render_board,
    render_fleet,
    render_next,
    render_plan,
    render_search,
    render_standup,
    render_update,
    render_view,
)
from ...usecases import ask, board, fleet, next_task, plan, search, standup, update
from . import arguments as arg
from .answers import Answer, answer, failure, from_engine

__all__ = ["call_tool", "HANDLERS"]

Handler = Callable[[dict[str, Any]], str]


def _plan(args: dict[str, Any]) -> str:
    return render_plan(plan(arg.repo(args), arg.entries(args),
                            actor=arg.optional(args, "actor")))


def _next(args: dict[str, Any]) -> str:
    return render_next(next_task(arg.repo(args), actor=arg.optional(args, "actor"),
                                 session=arg.optional(args, "session"),
                                 labels=arg.csv(args, "labels"),
                                 task=arg.optional(args, "task")))


def _update(args: dict[str, Any]) -> str:
    return render_update(update(arg.repo(args), arg.text(args, "task"),
                                actor=arg.optional(args, "actor"),
                                status=arg.optional(args, "status"),
                                comment=arg.optional(args, "comment"),
                                mentions=arg.csv(args, "mentions"),
                                blocked_on=arg.optional(args, "blocked_on"),
                                no_code=arg.flag(args, "no_code")))


def _ask(args: dict[str, Any]) -> str:
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


def _report(args: dict[str, Any]) -> str:
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


HANDLERS: dict[str, Handler] = {
    "taskops_plan": _plan,
    "taskops_next": _next,
    "taskops_update": _update,
    "taskops_ask": _ask,
    "taskops_report": _report,
}


def call_tool(name: str, args: dict[str, Any]) -> Answer:
    """Never raises for a failure anyone should expect.

    An unknown tool, an argument the model left out, an uninitialised project and a lost
    race for a lease are all ordinary traffic here, and each one is worth a sentence the
    agent can act on rather than a traceback the host swallows.
    """
    handler = HANDLERS.get(name)
    if handler is None:
        return failure(f"no tool named {name} — taskops serves "
                       f"{', '.join(sorted(HANDLERS))}", "unknown_tool")
    try:
        return answer(handler(args))
    except TaskopsError as err:
        return from_engine(err)
