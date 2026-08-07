"""The taskops server: boards mounted by name, one door each.

    POST /<board>/rpc            every verb, read and write
    GET  /<board>/feed           WebSocket (SSE fallback) — the UI's live wire
    POST /<board>/invite/redeem  burn an invite, get a personal credential
    GET  /<board>/ui/*           the bundle
    GET  /healthz

The boards themselves live in `mounts.py`; this file is only the router.
"""

from __future__ import annotations

import json
from typing import Any, cast
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

from . import rpc, feed, static
from .. import _clock
from .auth import Credential, authorize
from .._json import as_object
from .mounts import Mounts
from .._errors import Refused, BadRequest, TaskopsError

MAX_BODY = 4 * 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    server_version = "taskops"

    # HTTP/1.1, and not by taste: a WebSocket handshake is only valid over 1.1.
    # With the default 1.0 the status line reads "HTTP/1.0 101 …" and every
    # browser drops the connection — the UI would silently never go live, which
    # is precisely the kind of failure that hides for a week.
    protocol_version = "HTTP/1.1"

    @property
    def mounts(self) -> Mounts:
        """The server owns the boards; the handler borrows them."""
        return cast("BoardServer", self.server).mounts

    def do_POST(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's contract
        board, tail = _split(self.path)
        if tail == "rpc":
            self._rpc(board)
        elif tail == "invite/redeem":
            self._redeem(board)
        else:
            self._fail(404, BadRequest(f"nothing at {self.path}"))

    def do_GET(self) -> None:  # noqa: N802
        board, tail = _split(self.path)
        if self.path.rstrip("/") == "/healthz":
            self._json(200, {"ok": True, "seq": 0, "data": {"boards": self.mounts.count()}})
        elif tail == "feed":
            self._feed(board)
        elif tail.startswith("ui"):
            self._static(tail[2:])
        else:
            self._fail(404, BadRequest(f"nothing at {self.path}"))

    # BaseHTTPRequestHandler already logs one line per request to stderr, and
    # that is what we want: a broken server is seen, never swallowed. (Do not
    # "improve" it by overriding log_message to call log_error — that pair
    # calls back into each other and recurses until the stack ends.)

    # ── the verbs ───────────────────────────────────────────────────────────

    def _rpc(self, board: str) -> None:
        try:
            payload = self._body()
            verb = rpc.verb_of(payload)
            stores = self.mounts.stores(board)
            credential = self._credential(board, rpc.needs(verb))
            actor, args = rpc.rest_of(payload, credential.subject)
            authorize(credential, actor)
        except TaskopsError as err:
            self._fail(rpc.status_for(rpc.failure(err)), err)
            return
        body = rpc.dispatch(stores, verb, actor, args)
        if body.get("ok") and rpc.needs(verb) == "write":
            # AFTER the write is durable, never before (v1 published first).
            self.mounts.hub.publish(board, {"type": "change", "verb": verb, "seq": body["seq"]})
        self._json(rpc.status_for(body), body)

    def _redeem(self, board: str) -> None:
        try:
            payload = self._body()
            who = str(payload.get("who", "")).strip()
            token = str(payload.get("invite", "")).strip()
            if not who or not token:
                raise BadRequest('POST {"invite": "…", "who": "<your name>"}')
            fresh = self.mounts.credentials.redeem(token, board, who, _clock.now())
        except TaskopsError as err:
            self._fail(rpc.status_for(rpc.failure(err)), err)
            return
        self._json(200, {"ok": True, "seq": 0, "data": {"token": fresh, "actor": f"dev:{who}"}})

    def _feed(self, board: str) -> None:
        try:
            self.mounts.stores(board)
            self._credential(board, "read")
        except TaskopsError as err:
            self._fail(rpc.status_for(rpc.failure(err)), err)
            return
        wanted = self.headers.get("Upgrade", ""), self.headers.get("Sec-WebSocket-Key", "")
        # Somebody is looking now: watch the board for writes this process did
        # not make (every agent on a LOCAL board writes in its own process).
        self.mounts.watch(board)
        feed.attach(self, self.mounts.hub, board, *wanted)

    def _static(self, rest: str) -> None:
        path = static.resolve(self.mounts.ui, rest)
        if path is None:
            self._fail(404, BadRequest("no UI bundle is installed on this server"))
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", static.content_type(path))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ── plumbing ────────────────────────────────────────────────────────────

    def _credential(self, board: str, need: str) -> Credential:
        token = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not token:
            _, _, query = self.path.partition("?")
            for part in query.split("&"):
                if part.startswith(("token=", "invite=")):
                    token = part.partition("=")[2]
        if not token:
            raise Refused("no credential — run: taskops join <url with ?token= or ?invite=>")
        return self.mounts.credentials.check(token, board, need, _clock.now())

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > MAX_BODY:
            raise BadRequest("that request is too large for a board call")
        try:
            raw: object = json.loads(self.rfile.read(length) or b"{}")
        except ValueError as err:
            raise BadRequest(f"the body must be JSON: {err}") from err
        body = as_object(raw)
        if not body and not isinstance(raw, dict):
            raise BadRequest("the body must be a JSON object")
        return body

    def _json(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _fail(self, status: int, err: TaskopsError) -> None:
        self._json(status, rpc.failure(err))


def _split(path: str) -> tuple[str, str]:
    clean = path.partition("?")[0].strip("/")
    board, _, tail = clean.partition("/")
    return board, tail


class BoardServer(ThreadingHTTPServer):
    """A threading server that owns its mounts — no module-level state anywhere,
    so one process can run three independent boards without them seeing each other."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], mounts: Mounts) -> None:
        self.mounts = mounts
        super().__init__(address, Handler)

    def server_close(self) -> None:
        super().server_close()
        self.mounts.close()


def serve(
    root: Path, host: str = "127.0.0.1", port: int = 8787, ui: Path | None = None
) -> BoardServer:
    """A server, not yet running. The caller decides the thread and the lifetime."""
    return BoardServer((host, port), Mounts(root, ui))
