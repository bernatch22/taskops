"""What a tool call carries IN — the inputs, as types.

The MCP `inputSchema` is generated from these (`transports/mcp/schema.py`), so a parameter is
declared once and cannot exist on the wire without existing in the dispatch, or the reverse — which
is how a tool ends up advertising a flag nobody reads.

The description TEXT lives in `_fields`. It is the contract, not decoration — the only thing a
calling agent reads before choosing arguments — but it is prose, and keeping it out of here means a
change to a tool's SHAPE is reviewable on its own.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from . import _fields as f

__all__ = ["PlanParams", "NextParams", "UpdateParams", "AskParams", "ReportParams",
           "DispatchParams"]


class _Target(TypedDict):
    """Which repository. Every tool needs it; none of them guesses it."""

    repo_path: f.Repo


class _PlanRequired(_Target):
    tasks: Annotated[list[dict[str, Any]], f.TASKS]


class PlanParams(_PlanRequired, total=False):
    actor: f.Actor


class NextParams(_Target, total=False):
    actor: f.Actor
    session: f.Session
    labels: Annotated[str, f.LABELS]
    task: Annotated[str, f.CLAIM_ONE]


class _UpdateRequired(_Target):
    task: f.TaskId


class UpdateParams(_UpdateRequired, total=False):
    status: Annotated[Literal["in_progress", "blocked", "review", "done", "released",
                              "cancelled"], f.STATUS]
    comment: Annotated[str, f.COMMENT]
    mentions: Annotated[str, f.MENTIONS]
    blocked_on: Annotated[str, f.BLOCKED_ON]
    no_code: Annotated[bool, f.NO_CODE]


class AskParams(_Target, total=False):
    task: Annotated[str, f.ASK_TASK]
    query: Annotated[str, f.ASK_QUERY]


class DispatchParams(_Target, total=False):
    """Launch worker agents. The tool that turns a plan into work in flight."""

    tasks: Annotated[str, f.DISPATCH_TASKS]
    count: Annotated[int, f.DISPATCH_COUNT]
    prefix: Annotated[str, f.PREFIX]
    model: Annotated[str, f.MODEL]
    dry_run: Annotated[bool, f.DRY_RUN]
    actor: f.Actor


class ReportParams(_Target, total=False):
    kind: Annotated[Literal["board", "standup", "burndown", "fleet"], f.REPORT_KIND]
    actor: Annotated[str, f.REPORT_ACTOR]
    since: Annotated[str, f.SINCE]
