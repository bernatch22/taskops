"""One tool call -> the text the agent reads. A TABLE, never a chain of ifs.

The handlers live in `_reads` and `_writes`, split by what they DO rather than by tool count: one
group answers questions and changes nothing, the other enters a use case that enforces a rule. What is
left here is the routing and the ONE place a typed engine failure becomes a sentence an agent can act
on — which is the whole reason the CLI, MCP and HTTP surfaces cannot drift apart.
"""

from __future__ import annotations

from typing import Any, Callable

from ..._errors import TaskopsError
from . import _context as context
from . import _reads as read
from . import _writes as write
from .answers import Answer, answer, failure, from_engine

__all__ = ["call_tool", "HANDLERS"]

Handler = Callable[[dict[str, Any]], str]

HANDLERS: dict[str, Handler] = {
    "taskops_next": write.next_,
    "taskops_update": write.update_,
    "taskops_ask": read.ask_,
    "taskops_context": context.context_,
    "taskops_capture": write.capture_,
    "taskops_plan": write.plan_,
    "taskops_dispatch": write.dispatch_,
    "taskops_recover": write.recover_,
    "taskops_report": read.report_,
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
