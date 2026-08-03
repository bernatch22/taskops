"""Path and method -> a route. A TABLE, built once with the root and the policy bound in.

Same shape as the MCP dispatch and for the same reason: the table is the surface, so adding an
endpoint is a row here rather than a branch in a handler, and nothing can be reachable without
appearing in a list somebody can read.
"""

from __future__ import annotations

from pathlib import Path

from ...usecases.journal import journal
from . import static, unlock
from ._routes import table
from ._wire import Reply, Request, Route, error_reply
from .policy import Policy

__all__ = ["build"]


def build(root: Path, policy: Policy, base: str = "/") -> Route:
    """The one function the server calls per request. Everything else is bound here.

    `base` is the URL prefix this table was mounted under — `/` for `taskops ui`, `/<project>/`
    for one board inside `taskops serve`. It never reaches a route: paths arrive already
    trimmed, and the only thing that needs it is the `<base>` tag in `index.html`.
    """
    routes = table(root, policy)

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
