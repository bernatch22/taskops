"""THE surface, as data — every path this server answers, in one readable list.

Split out of `router` when it filled up, and the seam is worth stating: that module DISPATCHES
(policy, journal, the SPA fallback) and this one only says what exists. Nothing can be reachable
without appearing here, which is the property the split protects — a route added inside a handler
is a route no reviewer sees.
"""

from __future__ import annotations

from functools import partial
from pathlib import Path

from . import agentapi, api, assigning, exchange, invites, live, reports, rpc, unlock  # noqa: F401
from ._wire import Reply, Request, Route
from .context import get_context, get_milestones, get_task_context
from .policy import Policy

__all__ = ["table"]


def table(root: Path, policy: Policy) -> dict[tuple[str, str], Route]:
    """Both halves, merged. Two of them, and the seam is the METHOD: a GET answers with what the board is, a write changes
    it and passes through the journal below. Splitting on anything else would put a read and its
    write in different places, which is how a route gets added twice.
    """
    return {**_reads(root, policy), **_writes(root)}


def _reads(root: Path, policy: Policy) -> dict[tuple[str, str], Route]:
    """Everything a browser or a replica GETs."""
    return {
        ("GET", "/api/config"): partial(_config, root, policy),
        ("GET", "/api/board"): partial(api.get_board, root),
        ("GET", "/api/fleet"): partial(api.get_fleet, root),
        ("GET", "/api/standup"): partial(api.get_standup, root),
        ("GET", "/api/task"): partial(api.get_task, root),
        ("GET", "/api/search"): partial(api.get_search, root),
        ("GET", "/api/activity"): partial(api.get_activity, root),
        ("GET", "/api/context"): partial(get_context, root),
        # The slice for ONE card — what its worker was handed — under `/api/task/` because that
        # is what it is about: a card, read when a person opens it, not a second board-wide read.
        ("GET", "/api/task/context"): partial(get_task_context, root),
        # Every chapter, closed ones included — the record, not the slice. The UI's strip reads
        # the slice; its "ended" list reads this, and only when somebody asks for it.
        ("GET", "/api/milestones"): partial(get_milestones, root),
        ("GET", "/api/report"): partial(reports.get_report, root),
        ("GET", "/api/reports"): partial(reports.get_reports, root),
        ("GET", "/api/agents"): partial(assigning.get_agents, root),
        ("GET", "/api/live"): partial(live.stream, root),
        ("GET", "/api/sync"): partial(exchange.get_sync, root),
        ("GET", "/api/report/file"): partial(exchange.get_report_file, root),
    }


def _writes(root: Path) -> dict[tuple[str, str], Route]:
    """Everything that appends. `/api/rpc` is the one a replica routes its writes through."""
    return {
        ("POST", "/api/invite"): partial(invites.post_invite, root),
        ("POST", "/api/report/digest"): partial(reports.post_digest, root),
        ("POST", "/api/comment"): partial(api.post_comment, root),
        ("POST", "/api/status"): partial(api.post_status, root),
        ("POST", "/api/assign"): partial(assigning.post_assign, root),
        ("POST", "/api/sync"): partial(exchange.post_sync, root),
        ("PUT", "/api/report/file"): partial(exchange.put_report_file, root),
        ("POST", "/api/next"): partial(agentapi.post_next, root),
        ("POST", "/api/update"): partial(agentapi.post_update, root),
        ("POST", "/api/rpc"): partial(rpc.post_rpc, root),
    }


def _config(root: Path, policy: Policy, request: Request) -> Reply:
    """`readonly` reaches the UI through the request rather than through module state, so the
    endpoint stays a pure function of what it was given."""
    marked = Request(method=request.method, path=request.path,
                     query={**request.query, "_readonly": "1" if policy.readonly else "0"},
                     headers=request.headers, body=request.body)
    return api.config(root, marked)
