"""The two invite doors, and they sit on opposite sides of the board's gate on purpose.

`POST /<board>/api/invite` is UNDER the mount, so the existing `Policy` guards it and no new
authorisation is written: whoever may already write to this board — the token, or a session the
mount swapped for it — is exactly who may invite somebody to it. A second rule here would be a
second answer to "who owns this board".

`POST /api/invite/redeem` is at the ROOT, and it has to be: the person redeeming has no
credential yet, which is the entire point. The code IS the authorisation, which is why it is
single-use, expiring, hashed at rest and refused with one message however it failed.
"""

from __future__ import annotations

from pathlib import Path

from ..._errors import TaskopsError
from ...usecases.invites import offer, pending, redeem, withdraw
from ._wire import Reply, Request, error_reply, json_reply

__all__ = ["post_invite", "post_redeem"]


def post_invite(root: Path, request: Request) -> Reply:
    """`{who}` in, the code out — shown ONCE. `{who, withdraw: true}` takes one back.

    `root` here is the BOARD directory, because this route is mounted under it.
    """
    body = request.payload()
    who = str(body.get("who") or "")
    try:
        if body.get("withdraw"):
            return json_reply({"withdrawn": who, "was_pending": withdraw(root, who)})
        code = offer(root, who, str(body.get("by") or ""))
        return json_reply({"who": who, "code": code,
                           "pending": [i["who"] for i in pending(root)]})
    except TaskopsError as err:
        return error_reply(err.http_status, str(err), err.code)


def post_redeem(home: Path, request: Request) -> Reply:
    """`{board, code}` in, a session out. No credential required — the code is the credential.

    `home` is the SERVER root: the board is named in the body, because a caller with an invite
    knows which board they were invited to and nothing else about this server.
    """
    body = request.payload()
    try:
        return json_reply(redeem(home, str(body.get("board") or ""),
                                 str(body.get("code") or "")))
    except TaskopsError as err:
        return error_reply(err.http_status, str(err), err.code)
