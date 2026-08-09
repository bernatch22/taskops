"""The remote board a LOCAL window is a window onto — the one thing that differs.

`taskops ui` always serves the dashboard from the checkout it stands in. The
routes are the same in both modes (`/board/ui/`, `/board/rpc`, `/board/git/…`),
so the committed bundle never learns which kind of board it is talking to. The
whole difference is who answers `/rpc`:

    no url in the config:  verbs.call(the local stores, …)
    a url in the config:   this module, POSTing the SAME body to <url>/rpc
                           with the bearer out of `remote.json`

**Why forward rather than point the page at the remote.** The alternative was to
serve the bundle locally and have it call the server directly: absolute URLs in
the client, CORS on the server, and the team's credential handed to the browser
so it could sign those calls. Three surfaces touched for one result — and the
last of them is the one that decides it. Forwarding keeps the page on ONE base
URL with relative paths, so there is no CORS anywhere, no client change at all,
and **the team credential never leaves this process**: the browser only ever
holds the token `taskops ui` mints into `ui.json`, which is local, revocable and
worth nothing to anybody off this machine.

**The body is relayed verbatim, and so is the answer.** Nothing here reads the
verb's arguments, rewrites an actor or re-wraps a result: `board.py::RemoteBoard`
is the pattern, including its refusal handling. A remote refusal must reach the
page as the SERVER's own message and status — a board that says "held by
agent:berna/w1" with a 409 must not arrive as a local 500 with a traceback in
it, because then the reader is debugging this host instead of reading the board.
Only a server that could not be reached at all is spoken for here, and it says
so in the same envelope shape everything else uses.

**The feed is a poll, not a relay** (`feed.py`: a message is a SIGNAL, not a
payload). `mounts.py` asks `head()` on an interval while somebody is connected
and pokes the page when the number moves; the page then refetches through the
forward above. No WebSocket is proxied through the stdlib handler and no SSE
stream is bridged — a late or missed poke costs one tick and can never show
something the board did not say.
"""

from __future__ import annotations

import json
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

from .._json import as_object

TIMEOUT = 20.0
"""Seconds to wait on the remote for one /rpc. The same budget `board.py` gives
a RemoteBoard, and for the same reason: a board call is a request a human is
waiting on, not a background job."""


class Upstream:
    """One remote board, addressed by url, spoken to with one credential."""

    def __init__(self, url: str, token: str, timeout: float = TIMEOUT) -> None:
        self.url = url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def rpc(self, body: bytes) -> tuple[int, bytes]:
        """(status, bytes) — the remote's own answer, untouched.

        Returns rather than raises: this sits under an HTTP handler whose job is
        to hand the page what the board said, and a refusal IS an answer."""
        headers = {"Content-Type": "application/json"}
        if self.token:
            # No token is the VIEWER's window onto a public board: sending an
            # empty `Bearer ` would be a credential offered and refused, where
            # what is true is that there is none. The server reads that as `anon`.
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(  # noqa: S310 — the scheme comes from the board's own config
            f"{self.url}/rpc",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                return int(response.status), bytes(response.read())
        except HTTPError as err:
            return int(err.code), _kept(err)
        except (URLError, TimeoutError, OSError, ValueError) as err:
            return 502, _unreachable(f"{self.url} did not answer ({err})")

    def head(self) -> int:
        """The remote board's sequence, or 0 when it could not be asked.

        This is what the feed polls. It goes through the same door as everything
        else — one `board` call with this host's credential — so there is no
        second endpoint to keep authorised, and a server that is down simply
        stops poking instead of raising once a second."""
        status, answer = self.rpc(b'{"verb": "board", "args": {}}')
        return seq_of(answer) if status == 200 else 0


def seq_of(answer: bytes) -> int:
    """The `seq` out of an envelope, or 0. Never raises: a body that is not an
    envelope means the poke is skipped, which costs one tick."""
    try:
        parsed: object = json.loads(answer)
    except ValueError:
        return 0
    seq: object = as_object(parsed).get("seq", 0)
    return seq if isinstance(seq, int) else 0


def _kept(err: HTTPError) -> bytes:
    """An HTTP error still carries the board's own refusal — keep those bytes.

    Only a body that is not one of our envelopes is replaced, and then by an
    envelope saying exactly that, because the page's decoder has one shape to
    read and `rpc.py` exists to make the other case unwritable."""
    try:
        raw = bytes(err.read())
    except (OSError, ValueError):
        raw = b""
    try:
        body: object = json.loads(raw)
    except ValueError:
        body = None
    if "ok" in as_object(body):
        return raw
    return _unreachable(f"the board answered HTTP {err.code} ({err.reason})")


def _unreachable(message: str) -> bytes:
    """The one answer this module writes itself. The remote said nothing, so
    nothing was written there either — say that, the way board.py says it."""
    return json.dumps(
        {
            "ok": False,
            "error": {
                "code": "unreachable",
                "message": (
                    f"{message}. The board is the server's, so nothing was written. "
                    "Check the server, or your .taskops/remote.json credential."
                ),
            },
        }
    ).encode()
