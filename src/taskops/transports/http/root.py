"""The server's front door: `GET /`, and the two calls a login is made of.

Everything under `/<project>/` is one board behind one secret. This module is what sits ABOVE
that: the page a person reaches when they type the hostname, and the endpoints that turn a
GitHub token into a session. It is the only part of the server that is not about one project,
which is why it is not in `router` — that one is built per project and mounted.

**The page lists NOTHING without a session.** Served to anyone, it is an instruction and not
an index: naming the boards would hand every visitor the enumeration the per-project 404 is
built to deny. With a session in `localStorage` it asks `/api/projects` and renders the links
that came back — the list is computed by the server from the session, never guessed by the JS.

**HTML inline, no bundle, no dependency.** This page must work on a server whose UI was never
built, because "the boards are at these URLs" is exactly what you need when something is
wrong. It is a few hundred bytes and has no build step; the studio is untouched by it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..._errors import TaskopsError
from ...usecases._sessions import resolve
from ...usecases.accounts import authenticate
from ...usecases.boardrows import rows_for
from ._wire import Reply, Request, error_reply, json_reply
from .frontpage import PAGE
from .invites import post_redeem
from .newboard import post_board

__all__ = ["root_route", "bearer"]

def root_route(home: Path, request: Request, *, create: bool = True) -> Reply | None:
    """The routes that belong to the server rather than to a project, or None to fall through.

    None and not a 404: everything this does not name is a project path, and answering here
    would take `/axion/api/board` away from the mount.
    """
    if request.path in ("", "/"):
        return Reply(status=200, body=PAGE.encode("utf-8"),
                     headers={"Content-Type": "text/html; charset=utf-8"})
    if request.path == "/api/auth/github" and request.method == "POST":
        return _login(home, request)
    if request.path == "/api/boards" and request.method == "POST":
        return post_board(home, request, create)
    if request.path == "/api/invite/redeem" and request.method == "POST":
        return post_redeem(home, request)
    if request.path == "/api/projects" and request.method == "GET":
        return _projects(home, request)
    return None


def _login(home: Path, request: Request) -> Reply:
    """`{"github_token": …}` in, `{login, session, projects}` out. The typed error carries its
    own status, so 403 (no repository) and 502 (GitHub did not answer) are one line of code."""
    token = str(request.payload().get("github_token") or "")
    try:
        return json_reply(authenticate(home, token))
    except TaskopsError as err:
        return error_reply(err.http_status, str(err), err.code)


def _projects(home: Path, request: Request) -> Reply:
    """What this session opens. The ROW is `usecases.boardrows` — two of its three fields come
    off the disk, and a transport may not read that."""
    found: dict[str, Any] | None = resolve(home, bearer(request))
    if found is None:
        return error_reply(401, "that session is unknown or has expired — run "
                                "`taskops login <url>` again", "unauthorized")
    names: list[str] = list(found.get("projects") or [])
    return json_reply({"login": found.get("login", ""),
                       "projects": rows_for(home, names)})


def bearer(request: Request) -> str:
    """The presented credential, header or query. `?token=` is accepted for the same reason
    `Policy` accepts it: `EventSource` cannot send a header, and a rule that holds for one
    path is a rule somebody moves."""
    told = request.headers.get("authorization", "")
    return told[7:].strip() if told.lower().startswith("bearer ") else request.param("token")
