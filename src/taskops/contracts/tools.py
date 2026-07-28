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
           "DispatchParams", "RecoverParams", "ContextParams", "CaptureParams"]


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
    evidence: Annotated[str, f.EVIDENCE]
    no_evidence: Annotated[str, f.NO_EVIDENCE]


class _CaptureRequired(_Target):
    title: Annotated[str, f.TITLE]


class CaptureParams(_CaptureRequired, total=False):
    """One unplanned card, created and claimed. `title` is the only thing required, because the
    caller is mid-task and every extra required field is a reason to skip recording the work."""

    spec: Annotated[str, f.SPEC]
    files: Annotated[str, f.FILES]
    labels: Annotated[str, f.LABELS]
    acceptance: Annotated[str, f.ACCEPTANCE]
    priority: Annotated[int, f.PRIORITY]
    claim: Annotated[bool, f.CLAIM_IT]
    assign: Annotated[str, f.ASSIGN]
    actor: f.Actor
    session: f.Session


class ContextParams(_Target, total=False):
    """Reading the standing facts. There is no WRITE half on this surface on purpose: an
    objective or an invariant is a human's call about the project, and a worker that could
    restate one could quietly rewrite the rules it is judged against."""

    task: Annotated[str, f.CONTEXT_TASK]


class AskParams(_Target, total=False):
    task: Annotated[str, f.ASK_TASK]
    query: Annotated[str, f.ASK_QUERY]


class DispatchParams(_Target, total=False):
    """Prepare worker agents for cards. The caller spawns them as its own sub-agents.

    There is deliberately NO `spawn` field here, and its absence is the design rather than an
    omission. The use case can start detached processes and `taskops dispatch --spawn` does, because
    that is a human at a terminal asking for it — but a model calling a tool must not be able to make
    this package launch another Claude Code. An agent inside a session already HAS a way to run work
    in parallel: its own sub-agent tool, on the subscription that is already paid for. Spawning from
    here opens a new billed session per worker, which is how a real fleet drained an API balance
    mid-run and left six cards claimed by processes that no longer existed.

    A capability the engine has and a transport withholds is a normal thing for this codebase — the
    surfaces are thin, not identical.
    """

    tasks: Annotated[str, f.DISPATCH_TASKS]
    count: Annotated[int, f.DISPATCH_COUNT]
    prefix: Annotated[str, f.PREFIX]
    model: Annotated[str, f.MODEL]
    dry_run: Annotated[bool, f.DRY_RUN]
    actor: f.Actor


class RecoverParams(_Target, total=False):
    """Hand back the cards of workers that died. The other half of dispatching a fleet."""

    force: Annotated[bool, f.RECOVER_FORCE]
    grace: Annotated[int, f.RECOVER_GRACE]
    actor: f.Actor


class ReportParams(_Target, total=False):
    """The four views a model may ask for, and no more.

    `fleet` and `burndown` were advertised here and are not any more. One answered a question
    agents stopped having — "who is free" means nothing when a worker is created on demand,
    and the studio dropped the panel for the same reason — while the other was never
    implemented and replied with a sentence saying so. A tool that lists a kind an agent
    cannot use spends the description budget teaching it to pick wrong. `fleet` survives as a
    use case: the HTTP api still serves it, because a human looking at a board does want to
    know which claim has gone quiet.
    """

    kind: Annotated[Literal["board", "standup", "day", "range"], f.REPORT_KIND]
    actor: Annotated[str, f.REPORT_ACTOR]
    since: Annotated[str, f.SINCE]
    date: Annotated[str, f.DATE]
    last: Annotated[str, f.LAST]
    from_date: Annotated[str, f.FROM_DATE]
    to: Annotated[str, f.TO_DATE]
