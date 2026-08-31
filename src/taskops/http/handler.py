"""The request handler — one method per door, split out of `server.py` so the
router (the class) and the server's lifecycle (`BoardServer`, `serve`) each
have room. What each route MEANS is `server.py`'s docstring; this file is
only how one request travels through it (`routes.py` reads the path).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Callable, cast
from http.server import BaseHTTPRequestHandler

from . import rpc, feed, page, admin, login, static, gitdoor, gitpack
from .. import _clock
from .auth import Credential, token_in, anonymous
from .mounts import NAME
from .routes import split
from .._errors import BadRequest, TaskopsError
from .._version import __version__

if TYPE_CHECKING:
    from .mounts import Mounts
    from .server import BoardServer


class Handler(BaseHTTPRequestHandler):
    server_version = "taskops"

    # HTTP/1.1, and not by taste: a WebSocket handshake is only valid over 1.1. With the
    # default 1.0 the status line reads "HTTP/1.0 101 …" and every browser drops the
    # connection — the UI would silently never go live, which hides for a week.
    protocol_version = "HTTP/1.1"

    @property
    def mounts(self) -> Mounts:
        """The server owns the boards; the handler borrows them."""
        return cast("BoardServer", self.server).mounts

    def do_POST(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's contract
        self.mounts.touch()  # the window's idle clock (`cli/window.py`) reads this
        board, tail = split(self.path)
        if tail == "rpc":
            self._rpc(board)
        elif tail.startswith("repo.git/git-"):
            gitpack.serve(self, board, tail)  # the smart-HTTP exchange (push, fetch)
        elif tail == "invite/redeem":
            self._mint("redeem", board)
        elif board == "login" and not tail:
            self._mint("login", "")  # server scope: a key, not a board credential
        elif board == "rpc" and not tail:
            self._admin()  # the HOST's own verbs — one segment, so no board shadows it
        else:
            self._fail(404, BadRequest(f"nothing at {self.path}"))

    def do_GET(self) -> None:  # noqa: N802
        self.mounts.touch()
        board, tail = split(self.path)
        if self.path.rstrip("/") == "/healthz":
            data: dict[str, Any] = {"boards": self.mounts.count()}
            if self.mounts.repo is not None:
                # IDENTITY, and only for a WINDOW: `taskops ui` must be able to
                # tell "our window is up" from "something answered that port" —
                # reusing by liveness alone reopened tabs onto a four-day-old
                # binary (`cli/window.py`). A board HOST keeps the terse answer:
                # its healthz is public, and a server path in it is a leak.
                data["window"] = str(self.mounts.repo)
                data["version"] = __version__
            self._json(200, {"ok": True, "seq": 0, "data": data})
        elif tail == "feed":
            self._feed(board)
        elif tail == "repo.git/info/refs":
            gitpack.advertise(self, board)  # git's first ask, clone and push alike
        elif tail.startswith("git/"):
            self._git(board, tail[4:])
        elif tail.startswith("ui"):
            page.answer(self, board, tail[2:])  # 0.5.0's address, kept — links were pasted
        elif self.mounts.ui is None and NAME.match(board) and (not tail or static.asset(tail)):
            # the page at the board's OWN address; assets are a CLOSED set
            page.answer(self, board, tail)
        elif (found := static.at_root(self.mounts.ui, self.path)) is not None:
            self._send(200, *found)  # a WINDOW serves its page at the ROOT
        else:
            self._fail(404, BadRequest(f"nothing at {self.path}"))

    # BaseHTTPRequestHandler already logs one line per request to stderr, and that is what
    # we want: a broken server is seen, never swallowed. (Do not "improve" it by overriding
    # log_message to call log_error — that pair recurses until the stack ends.)

    # ── the verbs ───────────────────────────────────────────────────────────

    def _rpc(self, board: str) -> None:
        try:
            raw = self._raw()
            payload = rpc.decode(raw)
            verb = rpc.verb_of(payload)
            self.mounts.check(board)
            credential = self._credential(board, rpc.needs(verb))
            status, answer = rpc.answered(self.mounts, board, credential, verb, raw, payload)
        except TaskopsError as err:
            self._fail(rpc.status_for(rpc.failure(err)), err)
            return
        self._send(status, answer, "application/json")

    def _mint(self, door: str, board: str) -> None:
        """The two doors that hand out a CREDENTIAL — `login.py` owns both, so
        the router never learns what an invite or a signature is."""
        host, creds = self.mounts.host, self.mounts.credentials
        self._answer(lambda body: login.answer(host, creds, door, board, body, _clock.now()))

    def _admin(self) -> None:
        """The HOST's own verbs — `admin.py` owns the registry, the role gate, the
        session check, and the argument for why this door is the ROOT `/rpc`."""
        token = token_in(self.headers.get("Authorization", ""), self.path)
        self._answer(lambda body: admin.answer(self.mounts, token, body, _clock.now()))

    def _feed(self, board: str) -> None:
        try:  # no credential on a PUBLIC board: `feed.py`'s third rule says why
            self.mounts.check(board)
            self._credential(board, "read")
        except TaskopsError as err:
            self._fail(rpc.status_for(rpc.failure(err)), err)
            return
        wanted = self.headers.get("Upgrade", ""), self.headers.get("Sec-WebSocket-Key", "")
        # Somebody is looking now: watch the board for writes this process did not
        # make (every agent on a LOCAL board writes in its own process).
        self.mounts.watch(board)
        feed.attach(self, self.mounts.hub, board, *wanted)

    def _git(self, board: str, rest: str) -> None:  # same token door as /rpc
        self._answer(lambda _: self._diff(board, rest))

    def _diff(self, board: str, rest: str) -> dict[str, Any]:
        """A window answers from its own LOCAL clone; a serve-mode host from
        the board's forge mirror — `repos.py` decides which, per board (§16)."""
        self.mounts.check(board)
        self._credential(board, "read")
        repo, mirrored = self.mounts.repos.for_board(board)
        return gitdoor.answer(repo, rest, self.path.partition("?")[2], mirrored=mirrored)

    # `_static` moved whole to `page.py` when the git doors arrived — the budget
    # forced a split and the page policy was the cohesive cut.

    # ── plumbing ────────────────────────────────────────────────────────────

    def _answer(self, run: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        """Decode, run, envelope — every door but `/<board>/rpc`, which relays bytes.
        One copy, so a door added later cannot answer a shape of its own."""
        try:
            data = run(rpc.decode(self._raw()))
        except TaskopsError as err:
            self._fail(rpc.status_for(rpc.failure(err)), err)
            return
        self._json(200, {"ok": True, "seq": 0, "data": data})

    def _credential(self, board: str, need: str) -> Credential:
        """The token, or NOBODY — one method, so no door grants `anon` its own way."""
        token = token_in(self.headers.get("Authorization", ""), self.path)
        if not token:
            return anonymous(self.mounts.public(board), need)
        return self.mounts.credentials.check(token, board, need, _clock.now())

    def _raw(self) -> bytes:
        """BYTES: a forwarded `/rpc` is relayed as the page wrote it, never re-serialised."""
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > rpc.MAX_BODY:
            raise BadRequest("that request is too large for a board call")
        return self.rfile.read(length)

    def _json(self, status: int, body: dict[str, Any]) -> None:
        self._send(status, json.dumps(body).encode(), "application/json")

    def _send(self, status: int, data: bytes, kind: str) -> None:
        """Content-Length on EVERY answer: this is HTTP/1.1 with keep-alive, and a body
        without one leaves the next request on the socket unparseable."""
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _fail(self, status: int, err: TaskopsError) -> None:
        self._json(status, rpc.failure(err))
