"""Path and method -> a route. A TABLE, built once with the root and the policy bound in.

Same shape as the MCP dispatch and for the same reason: the table is the surface, so adding an
endpoint is a row here rather than a branch in a handler, and nothing can be reachable without
appearing in a list somebody can read.
"""

from __future__ import annotations

from functools import partial
from pathlib import Path

from ...usecases.journal import journal
from . import agentapi, api, assigning, exchange, invites, live, reports, rpc, static, unlock
from ._wire import Reply, Request, Route, error_reply

# Bound by NAME rather than through the module, unlike every row above: `from . import …, context`
# does not fit the line and the split form costs this module twelve lines of its code budget.
from .context import get_context, get_task_context
from .policy import Policy

__all__ = ["build"]


def _table(root: Path, policy: Policy) -> dict[tuple[str, str], Route]:
    """THE surface, as data. Its own function so `build` stays a dispatcher and the table can
    grow a row without the closure around it growing with it."""
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
        ("POST", "/api/invite"): partial(invites.post_invite, root),
        ("GET", "/api/report"): partial(reports.get_report, root),
        ("GET", "/api/reports"): partial(reports.get_reports, root),
        ("POST", "/api/report/digest"): partial(reports.post_digest, root),
        ("POST", "/api/comment"): partial(api.post_comment, root),
        ("POST", "/api/status"): partial(api.post_status, root),
        ("GET", "/api/agents"): partial(assigning.get_agents, root),
        ("POST", "/api/assign"): partial(assigning.post_assign, root),
        ("GET", "/api/live"): partial(live.stream, root),
        ("POST", "/api/sync"): partial(exchange.post_sync, root),
        ("GET", "/api/sync"): partial(exchange.get_sync, root),
        ("GET", "/api/report/file"): partial(exchange.get_report_file, root),
        ("PUT", "/api/report/file"): partial(exchange.put_report_file, root),
        ("POST", "/api/next"): partial(agentapi.post_next, root),
        ("POST", "/api/update"): partial(agentapi.post_update, root),
        ("POST", "/api/rpc"): partial(rpc.post_rpc, root),
    }


def build(root: Path, policy: Policy, base: str = "/") -> Route:
    """The one function the server calls per request. Everything else is bound here.

    `base` is the URL prefix this table was mounted under — `/` for `taskops ui`, `/<project>/`
    for one board inside `taskops serve`. It never reaches a route: paths arrive already
    trimmed, and the only thing that needs it is the `<base>` tag in `index.html`.
    """
    routes = _table(root, policy)

    def dispatch(request: Request) -> Reply:
        if refusal := policy.check(request):
            # The policy decides and never renders: `instead` passes every refusal through
            # untouched except a 401 on a browser NAVIGATION, which becomes the access screen.
            # See `unlock` for why the choice lives there rather than inside `Policy.check`.
            return unlock.instead(refusal, request, base)
        route = routes.get((request.method, request.path))
        if route is not None:
            answer = route(request)
            if request.method != "GET":
                # The journal, HERE, because this is the one door every write walks through —
                # a per-handler call is the pattern that already missed two handlers once.
                # Cheap on a no-op (one indexed query, zero rows) and never fatal: losing a
                # journal write must not fail the request whose events are safely in the db.
                try:
                    journal(root)
                except OSError:
                    pass
            return answer
        if request.method == "GET" and not request.path.startswith("/api/"):
            # Everything that is not the API is the single-page app, INCLUDING unknown paths:
            # the UI routes in the browser, so a reload on /task/tk-1 must serve index.html
            # rather than 404 — which is the classic broken-refresh bug in an SPA.
            return static.serve(request.path, base)
        return _no_route(request, routes)

    return dispatch


def _config(root: Path, policy: Policy, request: Request) -> Reply:
    """`readonly` reaches the UI through the request rather than through module state, so the
    endpoint stays a pure function of what it was given."""
    marked = Request(method=request.method, path=request.path,
                     query={**request.query, "_readonly": "1" if policy.readonly else "0"},
                     headers=request.headers, body=request.body)
    return api.config(root, marked)


def _no_route(request: Request, routes: dict[tuple[str, str], Route]) -> Reply:
    """405 when the path exists under another method, 404 otherwise.

    The two send a caller to completely different places, and "not found" for a GET on a POST
    route has cost everyone an afternoon at some point.
    """
    allowed = sorted({method for method, path in routes if path == request.path})
    if allowed:
        return error_reply(405, f"{request.path} accepts {', '.join(allowed)}",
                           "method_not_allowed")
    return error_reply(404, f"no route {request.path}", "no_such_route")
