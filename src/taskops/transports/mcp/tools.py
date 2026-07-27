"""The tools an agent can see — five, and each one earns its slot.

Every tool costs the calling agent context and a routing decision, so the surface carries
only what taskops alone can do: turn a plan into a persistent graph (`plan`), hand out work
without two agents taking the same piece (`next`), record what happened and tell somebody
(`update`), read a task's whole context (`ask`), and generate the report nobody wants to
write (`report`).

There is deliberately no sixth tool for messaging. Sending is `update` with `mentions`,
because a message about a task belongs in that task's thread — a separate chat tool would
produce conversations nobody can find later. Receiving is not a tool at all: the inbox rides
along with `next` and `ask`, and hooks deliver it between calls.

The description text lives in `_descriptions`, for the same reason the SQL lives in
`storage/_ddl` — reviewing a change here should not mean re-reading sixty lines of prose.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...contracts.tools import (
    AskParams,
    DispatchParams,
    NextParams,
    PlanParams,
    RecoverParams,
    ReportParams,
    UpdateParams,
)
from . import _descriptions as text
from .schema import json_schema

__all__ = ["Tool", "TOOLS", "listing"]


@dataclass(frozen=True, slots=True)
class Tool:
    """A name, what it is for, and the contract its arguments satisfy."""

    name: str
    description: str
    params: type[Any]


TOOLS: tuple[Tool, ...] = (
    Tool("taskops_next", text.NEXT, NextParams),
    Tool("taskops_update", text.UPDATE, UpdateParams),
    Tool("taskops_ask", text.ASK, AskParams),
    Tool("taskops_plan", text.PLAN, PlanParams),
    Tool("taskops_dispatch", text.DISPATCH, DispatchParams),
    Tool("taskops_recover", text.RECOVER, RecoverParams),
    Tool("taskops_report", text.REPORT, ReportParams),
)
"""Ordered by how often an agent needs them, not alphabetically.

With tool search on, a host may surface only the first few names, so `next` and `update` —
the two that carry every session — must not sit below the planning tool a session uses once.
"""


def listing() -> list[dict[str, Any]]:
    """The `tools/list` payload: description and schema, generated together."""
    return [{"name": tool.name, "description": tool.description,
             "inputSchema": json_schema(tool.params)} for tool in TOOLS]
