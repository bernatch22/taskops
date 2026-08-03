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

**Narration is isolated too, and not by this file.** A `WireMessage` rides a process-global
broadcast, so a browser watching one board could once see prose being written on another. It
was closed on the contract — a wire message carries the `root` that emitted it and
`usecases.feed.follow` filters on it — which is why the filter is not here: this module never
sees a frame.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from urllib.parse import urlencode

from ..._errors import TaskopsError
from ...contracts.hosting import NAME, TOKEN_FILE
from ...usecases import locate
from ...usecases._sessions import opens
from ...usecases.journal import reconcile
from ._wire import Reply, Request, Route, error_reply
from .policy import Policy
from .root import bearer, root_route
from .router import build

__all__ = ["mount", "NAME", "TOKEN_FILE"]
"""`NAME` and `TOKEN_FILE` are RE-EXPORTED, not defined: they moved to `contracts.hosting` when
provisioning became a use case, and they stay importable from here because this is where every
reader of this transport already looks for them."""


def mount(root: Path, *, readonly: bool = False, rate_limit: int = 0,
          create: bool = True) -> Route:
    """The root dispatcher for a directory of projects.

    Routers are CACHED per project. Building one opens a store, so constructing it per request
    would open and close sqlite on every poll of every board.

    `create` is remote board creation, open by default and off under `--readonly` — a server
    that refuses every write has no business minting a directory either.
    """
    home = Path(root).expanduser().resolve()
    cache: dict[str, tuple[Policy, Route]] = {}
    may_create = create and not readonly

    def dispatch(request: Request) -> Reply:
        if reply := root_route(home, request, create=may_create):
            return reply
        name, rest = _split(request.path)
        found = _project(home, name)
        if found is None:
            return error_reply(404, "no such project", "no_such_project")
        if name not in cache:
            cache[name] = _open(found, name, readonly=readonly, rate_limit=rate_limit)
        policy, route = cache[name]
        opened = _exchanged(home, name, _token(found), request)
        if not rest:
            # The redirect is gated too. It is a reply about a project, so handing it to an
            # unauthenticated caller would make `/name` a working existence oracle for every
            # board on the server — the one thing the bare 404 above exists to deny.
            #
            # Gated on the EXCHANGED request and redirected with the ORIGINAL one: a session
            # may pass the gate, but echoing the swapped query back would put the project's
            # own token — the machine credential — in the browser's address bar.
            return policy.check(opened) or _redirect(f"/{name}/", request)
        return route(replace(opened, path=rest))

    return dispatch


def _open(found: Path, name: str, *, readonly: bool,
          rate_limit: int) -> tuple[Policy, Route]:
    """Everything done ONCE per board per boot: repair its log, then build its router.

    The repair is for every board that predates the journal — four had full databases and
    0-byte logs. Never fatal: refusing to serve a board that cannot be journalled would turn a
    backup problem into an outage.
    """
    try:
        reconcile(found)
    except (OSError, ValueError):
        pass
    policy = Policy(token=_token(found), readonly=readonly, rate_limit=rate_limit)
    return policy, build(found, policy, base=f"/{name}/")


def _exchanged(home: Path, name: str, token: str, request: Request) -> Request:
    """A session that lists this project becomes this project's token, right here.

    The whole "a GitHub login opens a board" feature is this one substitution, and it lives at
    the MOUNT rather than inside `Policy` for a reason: sessions are a property of a directory
    of projects, and a policy built for one board has no way to know about a file one level
    up. Below this line nothing has heard of GitHub — the router, every endpoint and the feed
    see the ordinary bearer token they have always seen.

    A request that already carries the project's own token is untouched, so the machine
    credential (push, pull, agents) keeps working exactly as before. A string that is neither
    is left alone too, and refused by the policy with the message it always gave.
    """
    presented = bearer(request)
    if not presented or presented == token or not opens(home, presented, name):
        return request
    return replace(request, headers={**request.headers, "authorization": f"Bearer {token}"},
                   query={**request.query, "token": token})


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
