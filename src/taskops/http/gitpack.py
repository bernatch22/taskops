"""Git smart-HTTP under `/<board>/repo.git` — clone, fetch and PUSH against the
board's own repository (§16, "The host becomes the remote").

    GET  /<board>/repo.git/info/refs?service=git-upload-pack    (clone, fetch)
    GET  /<board>/repo.git/info/refs?service=git-receive-pack   (push, step 1)
    POST /<board>/repo.git/git-upload-pack
    POST /<board>/repo.git/git-receive-pack

**One credential path, and this is how git's shape maps onto it.** Git speaks
HTTP Basic; a taskops session token rides in Basic's PASSWORD field (the
username is decoration — `x` by convention), and `auth.token_in` unpacks it
back into the same bearer token every other door checks, so the check itself is
`handler._credential`, unchanged and unduplicated. READ (upload-pack) follows
the board's visibility exactly as /rpc does — a public board is world-clonable
and, running no verb, an anonymous clone writes nothing, no presence row (§11).
WRITE (receive-pack) is a write under §11's anonymous-write ban: it needs an
enrolled principal's credential with the `write` cap — `dev:` and `agent:`
alike, because workers are exactly who `bind.py` pushes as — and the refusal an
anonymous or read-only caller gets is the standing one that names the way in.
The split is asked ONCE, on the service name, before anything touches disk:
the ref advertisement for a push is already the push's first step, so it pays
the write check too — which is also what lets it CREATE `repo.git` on demand
(`gitwork/bare.py` argues why a read never creates it).

**The protocol is git's, spoken by git's own plumbing** through the one
subprocess module: `git {upload,receive}-pack --stateless-rpc`, request body to
stdin, stdout streamed to the socket chunk by chunk (`run.stream`). The one
piece of framing written here is the advertisement's two-packet service
preamble — that is smart-HTTP's TRANSPORT envelope (the same layer as `gitbody`'s
chunked decoding), not the pack protocol, which never gets reimplemented.

**Bodies are `gitbody.py`'s** — the HTTP framing half (chunked, gzip, and the
cap that replaces `rpc.MAX_BODY` here), split out where the seam owns no git.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from . import rpc, gitbody
from .._errors import Refused, NotFound, BadRequest, TaskopsError
from ..gitwork import run, bare

if TYPE_CHECKING:
    from .handler import Handler

UPLOAD = "git-upload-pack"
RECEIVE = "git-receive-pack"
FLUSH = "0000"

NOT_A_SERVICE = (
    "this door speaks git smart-HTTP only: info/refs?service=git-upload-pack or "
    "git-receive-pack, then the matching POST. The dumb protocol is not served "
    "— it reads loose files a bare repo is not required to have."
)

NOTHING_PUSHED = (
    "board {board!r} has no repository yet — one is created by its first push, "
    "never by a request to read one. `git push <this url> <branch>` from an "
    "enrolled checkout is the act that creates it."
)

def advertise(handler: Handler, board: str) -> None:
    """GET info/refs — the ref advertisement, first step of both clone and push."""
    service = _param(handler.path, "service")
    _door(handler, board, service, advert=True)


def serve(handler: Handler, board: str, tail: str) -> None:
    """POST git-upload-pack / git-receive-pack — the exchange itself."""
    _door(handler, board, tail.partition("/")[2], advert=False)


def _door(handler: Handler, board: str, service: str, *, advert: bool) -> None:
    """Every wall in order, then the stream. The credential comes BEFORE the
    body is read: a refused caller learns nothing about the repo and costs no
    memory; git re-POSTs with credentials on its own when the advertisement
    already passed."""
    try:
        if service not in (UPLOAD, RECEIVE):
            raise BadRequest(NOT_A_SERVICE)
        handler.mounts.check(board)
        writing = service == RECEIVE
        handler._credential(board, "write" if writing else "read")  # noqa: SLF001
        found = bare.at(handler.mounts.root / board)
        if found is None and writing:
            found = bare.ensure(handler.mounts.root / board)
        if found is None:
            raise NotFound(NOTHING_PUSHED.format(board=board))
        body = b"" if advert else gitbody.read(handler.headers, handler.rfile)
    except Refused as err:
        _challenge(handler, err)
        return
    except TaskopsError as err:
        handler._fail(rpc.status_for(rpc.failure(err)), err)  # noqa: SLF001
        return
    _stream(handler, str(found), service, advert=advert, body=body)


def _challenge(handler: Handler, err: Refused) -> None:
    """A Refused HERE is a 401 bearing `WWW-Authenticate`, not /rpc's 409 — by
    the client's contract, not taste: git volunteers Basic only AFTER a 401
    challenge (a first request always arrives bare, even with a token in the
    URL), so a 409 reads as "the URL is broken" and git never sends the
    credential it was holding. The refusal's own sentence still travels as the
    body, so a caller who reads it is told the way in, exactly as everywhere."""
    data = json.dumps(rpc.failure(err)).encode()
    handler.send_response(401)
    handler.send_header("WWW-Authenticate", 'Basic realm="taskops"')
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _stream(handler: Handler, repo: str, service: str, *, advert: bool, body: bytes) -> None:
    """Run the plumbing and put its stdout on the wire.

    The advertisement is small and is buffered so a failure can still answer as
    one (500, git's words logged); the pack exchange is streamed under chunked
    transfer-encoding because its length is unknowable until git is done. Git's
    exit code after bytes have flowed is git's ANSWER — a refused push (deny
    config, bad pack) travels inside the protocol stream itself and the client
    prints it — so a nonzero code then is logged, never turned into a second,
    unparseable HTTP error."""
    kind = f"application/x-{service}-{'advertisement' if advert else 'result'}"
    verb = service.removeprefix("git-")
    args = [verb, "--stateless-rpc", *(["--advertise-refs"] if advert else []), repo]
    proto = handler.headers.get("Git-Protocol", "")
    env = {"GIT_PROTOCOL": proto} if proto else None
    if advert:
        parts: list[bytes] = []
        code, err = run.stream(args, body, parts.append, env)
        if code != 0:
            fault = Refused(f"git {verb} could not advertise: {err or f'exit {code}'}")
            handler._fail(500, fault)  # noqa: SLF001
            return
        head = f"# service={service}\n"
        preamble = f"{len(head) + 4:04x}{head}{FLUSH}".encode()
        handler._send(200, preamble + b"".join(parts), kind)  # noqa: SLF001
        return
    handler.send_response(200)
    handler.send_header("Content-Type", kind)
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Transfer-Encoding", "chunked")
    handler.end_headers()

    def sink(data: bytes) -> None:
        if data:
            handler.wfile.write(b"%x\r\n%s\r\n" % (len(data), data))

    code, err = run.stream(args, body, sink, env)
    handler.wfile.write(b"0\r\n\r\n")
    if code != 0 and err:
        handler.log_error("git %s: %s", verb, err)


def _param(path: str, key: str) -> str:
    for part in path.partition("?")[2].split("&"):
        name, _, value = part.partition("=")
        if name == key:
            return value
    return ""
