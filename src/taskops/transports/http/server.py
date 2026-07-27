"""The wire: stdlib `ThreadingHTTPServer`, and the one handler that knows about HTTP.

Threaded and not async, which is the whole reason SSE works here at all: every live browser holds
a thread parked in a generator, and the sync engine underneath never has to know. A handful of
threads for a handful of tabs is the right size — this is a local tool, not a service.

Nothing in this file decides anything. It parses a request into a `Request`, hands it to the
route table, and writes back a `Reply`.
"""

from __future__ import annotations

import socket
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from ._wire import Reply, Request, Route
from .policy import Policy
from .router import build

__all__ = ["build_server", "bound_port"]

_MAX_BODY = 1 << 20
"""1 MB. Everything this API accepts is a comment and a task id; anything larger is a mistake or
a probe, and reading it into memory first is how a small server becomes a target."""


def build_server(host: str, port: int, root: Path, policy: Policy) -> ThreadingHTTPServer:
    """A server ready to `serve_forever`. Returned rather than run, so a test can bind port 0."""
    route = build(root, policy)

    class Handler(_Handler):
        dispatch = staticmethod(route)

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def bound_port(server: ThreadingHTTPServer) -> int:
    """The port actually bound. With `--port 0` the OS chooses, and this is how it gets said."""
    return int(server.socket.getsockname()[1])


class _Handler(BaseHTTPRequestHandler):
    dispatch: Route
    protocol_version = "HTTP/1.1"
    """1.1 for keep-alive, which SSE needs. It also obliges every reply to carry an accurate
    Content-Length — `_send` does, and a streamed reply omits it deliberately."""

    def do_GET(self) -> None:                                        # noqa: N802 — stdlib name
        self._handle()

    def do_POST(self) -> None:                                       # noqa: N802
        self._handle()

    def log_message(self, format: str, *args: Any) -> None:
        """Silent. The default logs every request to stderr, which buries the one line the studio
        prints — the URL a person needs — under a scrolling access log of its own polling."""
        return

    def handle_error(self, *args: Any) -> None:
        """A client that disconnects is NOT an error, and socketserver prints a traceback for it.

        Closing a tab resets a keep-alive connection, so the default behaviour puts a ten-line
        traceback on the console every time somebody closes the board. Everything that IS an error
        is already caught in `_handle` and answered with a 500.
        """
        return

    def _handle(self) -> None:
        try:
            reply = type(self).dispatch(self._request())
        except Exception as err:                       # noqa: BLE001 — a handler must not die
            # A raised handler kills the thread and the browser sees a dropped connection with no
            # explanation. One 500 with the exception text is worth far more than a clean stack in
            # a log nobody is reading.
            self._send(Reply(status=500, body=f"{type(err).__name__}: {err}".encode()))
            return
        self._send(reply)

    def _request(self) -> Request:
        parts = urlsplit(self.path)
        length = min(int(self.headers.get("Content-Length") or 0), _MAX_BODY)
        return Request(method=self.command, path=parts.path,
                       query=dict(parse_qsl(parts.query)),
                       headers={k.lower(): v for k, v in self.headers.items()},
                       body=self.rfile.read(length) if length else b"")

    def _send(self, reply: Reply) -> None:
        self.send_response(reply.status)
        for name, value in reply.headers.items():
            self.send_header(name, value)
        if reply.stream is None:
            self.send_header("Content-Length", str(len(reply.body)))
            self.end_headers()
            self.wfile.write(reply.body)
            return
        self.end_headers()
        self._pump(reply)

    def _pump(self, reply: Reply) -> None:
        """Write frames until the client disconnects, then CLOSE the generator.

        The broken-pipe catch is not defensive noise: closing a tab is the normal way an SSE
        response ends, so it must be an ordinary return rather than a traceback per closed tab.
        `flush` after every frame is what makes it live instead of buffered.

        The explicit `close()` is the important line, and it was measured into existence. A streamed
        body holds a sqlite connection and an event-bus subscription, released by the generator's
        own `finally` — but on a broken pipe the exception's traceback forms a reference cycle
        through this frame, so refcounting does not reclaim the generator and the cyclic collector
        gets to it whenever it likes. Subscriptions were still alive seven seconds after the client
        hung up. `closing()` runs that `finally` now, deterministically.
        """
        if reply.stream is None:
            return
        with closing(reply.stream()) as frames:
            try:
                for chunk in frames:
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, socket.timeout):
                return
