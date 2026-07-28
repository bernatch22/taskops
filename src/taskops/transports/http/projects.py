"""Many boards on one port: `/<project>/api/...` and `/<project>/` for each project's UI.

The whole design is one sentence: a project is the router that already exists, MOUNTED. This
module splits the first path segment off, finds the project it names, and hands the request to
`router.build` with the prefix trimmed — so every endpoint, the SSE feed and the websocket work
under a prefix without a single one of them learning that prefixes exist.

**Isolation is structural, not checked per endpoint.** A mounted router is bound to one root, so
a request that arrived under `/axion/` has no way to name another project's store: the only path
a route ever sees has already had its prefix removed. The name is validated against a strict
pattern BEFORE the filesystem is touched, so `..` and `/` are refused as syntax rather than
caught later by a resolve.

**A miss is a bare 404.** Naming the projects that do exist would hand an unauthenticated caller
the list of every board on the server, which is exactly the enumeration a per-project token is
there to prevent. The reply says nothing, including whether the name was wrong or the secret was.

**One known leak, written down rather than hidden**: `WireMessage` (a narration delta) is
published on a process-global bus and carries no project, so a browser watching one board can
see the prose of a report being written on another. Events cannot leak — they come from each
project's own sqlite — and closing the narration hole needs a field on the contract, which is a
change to the wire format rather than to this file.
"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlencode

from ..._errors import TaskopsError
from ...usecases import locate
from ._wire import Reply, Request, Route, error_reply
from .policy import Policy
from .router import build

__all__ = ["mount", "NAME", "TOKEN_FILE"]

NAME = re.compile(r"^[a-z0-9-]{1,40}$")
"""What may name a project. Deliberately narrower than "a valid directory name": lowercase,
digits and dashes only, so a project name is also a URL segment nobody has to escape — and
`..`, `/`, an empty string and a leading dot are all refused by the pattern itself."""

TOKEN_FILE = "token"
"""The project's secret, `0600`, minted by `taskops serve init`. A project without one is not
served AT ALL, rather than served open: this transport is meant to face the internet, and the
failure mode of the alternative is a board that is public because a file was missing."""


def mount(root: Path, *, readonly: bool = False, rate_limit: int = 0) -> Route:
    """The root dispatcher for a directory of projects.

    Routers are CACHED per project. Building one opens a store, so constructing it per request
    would open and close sqlite on every poll of every board.
    """
    home = Path(root).expanduser().resolve()
    cache: dict[str, tuple[Policy, Route]] = {}

    def dispatch(request: Request) -> Reply:
        name, rest = _split(request.path)
        found = _project(home, name)
        if found is None:
            return error_reply(404, "no such project", "no_such_project")
        if name not in cache:
            policy = Policy(token=_token(found), readonly=readonly, rate_limit=rate_limit)
            cache[name] = (policy, build(found, policy, base=f"/{name}/"))
        policy, route = cache[name]
        if not rest:
            # The redirect is gated too. It is a reply about a project, so handing it to an
            # unauthenticated caller would make `/name` a working existence oracle for every
            # board on the server — the one thing the bare 404 above exists to deny.
            return policy.check(request) or _redirect(f"/{name}/", request)
        return route(replace(request, path=rest))

    return dispatch


def _split(path: str) -> tuple[str, str]:
    """`/axion/api/board` -> `axion`, `/api/board`. An empty rest means the prefix had no
    trailing slash, which is a redirect rather than a route — the UI's relative URLs would
    otherwise resolve one level too high."""
    name, slash, rest = path.lstrip("/").partition("/")
    return name, f"/{rest}" if slash else ""


def _project(home: Path, name: str) -> Path | None:
    """The project directory, or None. The pattern is checked BEFORE any path is built.

    `locate` walking UP is the subtlety: a plain directory under the root would resolve to some
    ancestor project, so the answer only counts when it is the directory we asked about.
    """
    if not NAME.match(name):
        return None
    candidate = home / name
    try:
        found = locate(candidate)
    except (TaskopsError, OSError):
        return None
    return candidate if found == candidate and _token(candidate) else None


def _token(project: Path) -> str:
    try:
        return (project / TOKEN_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _redirect(location: str, request: Request) -> Reply:
    """308 and not 302: the method must survive, or a POST to `/axion` would silently become a
    GET. The query is carried across by hand — a redirect that dropped it would strip the
    `?token=` out of the very link `serve init` printed, and the board would 401 on arrival."""
    query = urlencode(request.query)
    return Reply(status=308, headers={"Location": f"{location}?{query}" if query else location})
