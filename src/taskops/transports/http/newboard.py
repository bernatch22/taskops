"""`POST /api/boards` — the door that removes the ssh from starting a board.

Its own module rather than another branch in `root`, which is about the FRONT PAGE and the two
calls a login is made of. This one writes to disk and mints a directory, which is a different
kind of endpoint and the only one on this server that creates rather than reads or relays.

Everything it decides lives in `usecases.hosting`; what is here is the shape of the request and
the one deployment question a use case cannot answer — whether this box accepts boards from
somebody's laptop at all.
"""

from __future__ import annotations

from pathlib import Path

from ..._errors import TaskopsError
from ...usecases.hosting import create_hosted, create_open
from ._wire import Reply, Request, error_reply, json_reply

__all__ = ["post_board"]


def post_board(home: Path, request: Request, allowed: bool) -> Reply:
    """`{name}` in, a board out — plus `github_token`/`github` when there IS a repository.

    Two boards come out of this one route because there are two, and the difference is what
    the caller gets back: with a repository, a SESSION, because GitHub already said who they
    are; without one, the board's TOKEN, because nothing else can.

    Open by default, closable with `taskops serve --no-create`: your own box should let you
    start a board from your laptop, a box facing strangers should not — and the tokenless path
    is anonymous, so on a public box that flag is the whole access control.
    """
    if not allowed:
        return error_reply(403, "this server does not accept boards created remotely — ask "
                                "whoever runs it, or start it without `--no-create`", "no_access")
    body = request.payload()
    name, github = str(body.get("name") or ""), str(body.get("github") or "")
    try:
        # NO `github` is not a malformed request, it is the other kind of board — one with no
        # access list to check against, whose credential is the token this hands back. Branched
        # on the field rather than on a mode flag: the client that has a repository sends one,
        # the client that does not cannot, and neither has to be told which door it is at.
        if not github:
            return json_reply(create_open(home, name, str(body.get("login") or "")))
        return json_reply(create_hosted(home, str(body.get("github_token") or ""), name, github))
    except TaskopsError as err:
        return error_reply(err.http_status, str(err), err.code)
