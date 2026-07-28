"""The websocket, against a real socket and a real second process.

The framing is unit-tested from literals (`tests/transports/test_wsframes.py`); this asserts the part
only a running server can: that the handshake completes, that a write from ANOTHER PROCESS arrives as
a text frame, and that the same route still speaks SSE to a client that does not upgrade.

The client here is hand-rolled for the same reason the server is — no dependency — and it doubles as
the proof that our own frames are readable by something that did not produce them.
"""

from __future__ import annotations

import io
import json
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Iterator

import pytest

from taskops.transports.http import Policy, bound_port, build_server
from taskops.transports.http import websocket as ws
from taskops.usecases import init, locate, plan

DEADLINE = 15.0


@pytest.fixture
def project(tmp_path: Path) -> Path:
    init(tmp_path, install_git_hooks=False)
    return tmp_path


@pytest.fixture
def server(project: Path) -> Iterator[int]:
    running = build_server("127.0.0.1", 0, locate(project), Policy())
    threading.Thread(target=running.serve_forever, daemon=True).start()
    try:
        yield bound_port(running)
    finally:
        running.shutdown()
        running.server_close()


class Client:
    """A minimal websocket client: connect, upgrade, read frames, close.

    Deliberately not a library. If our server's framing is wrong, a client built from the same
    understanding might be wrong in the same way — so the ASSERTIONS check protocol facts a browser
    would also check: the accept key, the opcode, and that the payload is valid JSON.
    """

    def __init__(self, port: int, path: str = "/api/live") -> None:
        self.key = ws.new_key()
        self.socket = socket.create_connection(("127.0.0.1", port), timeout=DEADLINE)
        request = (f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
                   f"Upgrade: websocket\r\nConnection: keep-alive, Upgrade\r\n"
                   f"Sec-WebSocket-Key: {self.key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.socket.sendall(request.encode())
        self.stream = self.socket.makefile("rb")
        self.status, self.headers = self._read_handshake()

    def _read_handshake(self) -> tuple[int, dict[str, str]]:
        status_line = self.stream.readline().decode("latin-1").strip()
        code = int(status_line.split(" ")[1]) if " " in status_line else 0
        headers: dict[str, str] = {}
        while True:
            line = self.stream.readline().decode("latin-1").strip()
            if not line:
                break
            name, _, value = line.partition(":")
            headers[name.strip().lower()] = value.strip()
        return code, headers

    def frame(self) -> tuple[int, bytes] | None:
        return ws.read_frame(self.stream)

    def until_text(self, needle: str) -> str:
        """Read frames until a TEXT frame contains `needle`. Pings are skipped, not treated as data —
        a test that accepted a ping as its answer would pass against a server sending nothing."""
        deadline = time.monotonic() + DEADLINE
        while time.monotonic() < deadline:
            got = self.frame()
            if got is None:
                return ""
            opcode, payload = got
            if opcode == ws.OPCODE_TEXT and needle in payload.decode("utf-8", "replace"):
                return payload.decode("utf-8")
        return ""

    def close(self) -> None:
        self.stream.close()
        self.socket.close()


def write_from_another_process(root: Path, task_id: str, text: str) -> None:
    subprocess.run([sys.executable, "-c", _WRITE, str(root), task_id, text],
                   capture_output=True, check=True, timeout=60)


_WRITE = ("import sys; from taskops.usecases import update; "
          "update(sys.argv[1], sys.argv[2], comment=sys.argv[3], actor='agent:ana/two')")
"""The use case, in a separate interpreter. It used to be `-m taskops.transports.cli.main
update`, which stopped existing when the agent protocol left the CLI for MCP — and what this
test needs is another PROCESS writing, not a particular spelling of the write."""


def test_the_handshake_completes_with_the_right_accept_key(server: int) -> None:
    """A browser REJECTS a handshake whose accept key does not hash its own key with the RFC's magic
    GUID, and the symptom is a socket that closes with no explanation. So the key is the assertion."""
    client = Client(server)
    try:
        assert client.status == 101
        assert client.headers["upgrade"].lower() == "websocket"
        assert client.headers["sec-websocket-accept"] == ws.accept_key(client.key)
    finally:
        client.close()


def test_the_feed_opens_with_a_hello_frame(server: int) -> None:
    client = Client(server)
    try:
        assert json.loads(client.until_text("hello"))["type"] == "hello"
    finally:
        client.close()


def test_a_write_from_another_process_arrives_as_a_text_frame(project: Path,
                                                              server: int) -> None:
    """THE test, and the reason the feed polls a cursor rather than only listening to the in-process
    bus: every agent is its own process, so a design that only saw its own writes would pass a
    same-process test and fail in every real deployment."""
    task_id = plan(project, [{"title": "Watched", "spec": "x"}])["created"][0]["id"]
    client = Client(server)
    try:
        assert client.until_text("hello")
        threading.Thread(target=write_from_another_process,
                         args=(project, task_id, "from another process"),
                         daemon=True).start()
        frame = client.until_text("from another process")
        payload = json.loads(frame)
        assert payload["type"] == "change"
        assert payload["event"]["body"]["text"] == "from another process"
        assert payload["event"]["task"] == task_id
    finally:
        client.close()


def test_a_quiet_feed_pings_rather_than_going_silent(project: Path,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    """A PING and not a text frame: it is the protocol's own liveness probe, so a browser answers it
    and can tell an idle board from a dead socket — which an SSE comment cannot do."""
    from taskops.transports.http import live

    monkeypatch.setattr(live, "KEEPALIVE_TICKS", 2)
    running = build_server("127.0.0.1", 0, locate(project), Policy())
    threading.Thread(target=running.serve_forever, daemon=True).start()
    client = Client(bound_port(running))
    try:
        client.until_text("hello")
        deadline = time.monotonic() + DEADLINE
        while time.monotonic() < deadline:
            got = client.frame()
            assert got is not None, "the stream ended instead of pinging"
            if got[0] == ws.OPCODE_PING:
                return
        pytest.fail("no ping within the deadline")
    finally:
        client.close()
        running.shutdown()
        running.server_close()


def test_the_same_route_still_speaks_sse_without_an_upgrade(server: int) -> None:
    """The fallback has to keep working, because a proxy that mangles upgrades is a real deployment —
    and because `curl -N /api/live` is how anybody debugs this."""
    connection = socket.create_connection(("127.0.0.1", server), timeout=DEADLINE)
    try:
        connection.sendall(b"GET /api/live HTTP/1.1\r\nHost: x\r\n\r\n")
        head = connection.recv(4096).decode("latin-1")
        assert "200 OK" in head
        assert "text/event-stream" in head
    finally:
        connection.close()


def test_an_upgrade_still_honours_the_token(project: Path) -> None:
    """The policy runs before the route, so it must refuse an upgrade too — otherwise the websocket
    would be the one endpoint a token does not protect."""
    running = build_server("127.0.0.1", 0, locate(project), Policy(token="s3cret"))
    threading.Thread(target=running.serve_forever, daemon=True).start()
    port = bound_port(running)
    try:
        refused = Client(port)
        assert refused.status == 401
        refused.close()
        allowed = Client(port, "/api/live?token=s3cret")
        assert allowed.status == 101
        allowed.close()
    finally:
        running.shutdown()
        running.server_close()


def test_reading_a_short_read_assembles_the_whole_frame() -> None:
    """`_exactly` loops, and this is why: a socket read may return fewer bytes than asked for, and
    treating a short read as a complete frame is the bug that works on localhost and corrupts frames
    over a real network."""
    class Dribbling(io.RawIOBase):
        def __init__(self, data: bytes) -> None:
            self.data = data
            self.at = 0

        def read(self, size: int = -1) -> bytes:      # noqa: ARG002 — one byte at a time
            if self.at >= len(self.data):
                return b""
            self.at += 1
            return self.data[self.at - 1:self.at]

    masked = _client_text_frame("hello there")
    got = ws.read_frame(Dribbling(masked))            # type: ignore[arg-type]
    assert got is not None
    assert got[0] == ws.OPCODE_TEXT
    assert got[1].decode() == "hello there"


def _client_text_frame(text: str) -> bytes:
    """A MASKED text frame, as a client must send. Built here rather than reusing the server's
    builder, because the server never masks — so this is the only way to exercise unmasking."""
    body = text.encode()
    mask = b"\x01\x02\x03\x04"
    masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(body))
    return bytes([0x81, 0x80 | len(body)]) + mask + masked
