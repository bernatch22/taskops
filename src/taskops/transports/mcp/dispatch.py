"""One tool call -> the text the agent reads. A TABLE, never a chain of ifs.

The handlers live in `_handlers`; what is left here is the routing and the ONE place a typed engine
failure becomes a sentence an agent can act on. That is the whole reason the CLI, MCP and HTTP
surfaces cannot drift — none of them is where a decision lives.
"""

from __future__ import annotations

from typing import Any, Callable

from ..._errors import TaskopsError
from . import _handlers as h
from .answers import Answer, answer, failure, from_engine

__all__ = ["call_tool", "HANDLERS"]

Handler = Callable[[dict[str, Any]], str]

HANDLERS: dict[str, Handler] = {
    "taskops_plan": h.plan_,
    "taskops_next": h.next_,
    "taskops_update": h.update_,
    "taskops_ask": h.ask_,
    "taskops_dispatch": h.dispatch_,
    "taskops_report": h.report_,
}


def call_tool(name: str, args: dict[str, Any]) -> Answer:
    """Never raises for a failure anyone should expect.

    An unknown tool, an argument the model left out, an uninitialised project and a lost race for a
    lease are all ordinary traffic here, and each one is worth a sentence the agent can act on rather
    than a traceback the host swallows.
    """
    handler = HANDLERS.get(name)
    if handler is None:
        return failure(f"no tool named {name} — taskops serves "
                       f"{', '.join(sorted(HANDLERS))}", "unknown_tool")
    try:
        return answer(handler(args))
    except TaskopsError as err:
        return from_engine(err)
