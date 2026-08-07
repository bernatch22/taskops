"""The live feed for the UI: WebSocket, with Server-Sent Events as the fallback.

Two rules, both learned the hard way in v1:

* **Publish AFTER the transaction commits.** v1 published first and the
  subscriber refetched a row that was not visible yet, wasting the tick.
* **A message is a SIGNAL, not a payload.** The UI refetches when poked, so a
  dropped or duplicated message can never leave it showing something the board
  never said. The connection is recycled by wall-clock seconds, not by "ticks
  without data".

Agents do not use this: their live channel is the pulse line that rides along
with every tool result.
"""

from __future__ import annotations

import json
import struct
from queue import Empty, Queue
from base64 import b64encode
from typing import Any, Protocol
from hashlib import sha1
from threading import Lock


class Writer(Protocol):
    """Whatever the handler hands us — a socket's buffered writer, or a fake."""

    def write(self, data: bytes, /) -> Any: ...

    def flush(self) -> None: ...


class Responder(Protocol):
    """The slice of an HTTP handler this module needs to answer a stream."""

    wfile: Any

    def send_response(self, code: int, message: str | None = None) -> None: ...

    def send_header(self, keyword: str, value: str) -> None: ...

    def end_headers(self) -> None: ...


GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
PING_SECONDS = 2.0
MAX_QUEUE = 64


class Hub:
    """Board name -> subscribers. One lock, no per-message allocation games."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._subs: dict[str, list[Queue[dict[str, Any]]]] = {}

    def subscribe(self, board: str) -> Queue[dict[str, Any]]:
        queue: Queue[dict[str, Any]] = Queue(maxsize=MAX_QUEUE)
        with self._lock:
            self._subs.setdefault(board, []).append(queue)
        return queue

    def unsubscribe(self, board: str, queue: Queue[dict[str, Any]]) -> None:
        with self._lock:
            listeners = self._subs.get(board, [])
            if queue in listeners:
                listeners.remove(queue)

    def publish(self, board: str, message: dict[str, Any]) -> None:
        """Called after the write is durable. A full queue means a stuck client:
        drop the message, never block the writer."""
        with self._lock:
            listeners = list(self._subs.get(board, []))
        for queue in listeners:
            if not queue.full():
                queue.put_nowait(message)

    def count(self, board: str) -> int:
        with self._lock:
            return len(self._subs.get(board, []))


def accept_key(key: str) -> str:
    return b64encode(sha1(key.encode() + GUID).digest()).decode()  # noqa: S324 — RFC 6455


def text_frame(payload: str) -> bytes:
    """A server frame: FIN + opcode 1, never masked (RFC 6455 §5.1)."""
    data = payload.encode("utf-8")
    if len(data) < 126:
        header = struct.pack("!BB", 0x81, len(data))
    elif len(data) < (1 << 16):
        header = struct.pack("!BBH", 0x81, 126, len(data))
    else:
        header = struct.pack("!BBQ", 0x81, 127, len(data))
    return header + data


def ping_frame() -> bytes:
    return struct.pack("!BB", 0x89, 0)


def pump_websocket(out: Writer, queue: Queue[dict[str, Any]]) -> None:
    """Send hello, then messages, then a ping every couple of seconds forever."""
    _send(out, text_frame(json.dumps({"type": "hello"})))
    while True:
        try:
            message = queue.get(timeout=PING_SECONDS)
        except Empty:
            if not _send(out, ping_frame()):
                return
            continue
        if not _send(out, text_frame(json.dumps(message))):
            return


def pump_events(out: Writer, queue: Queue[dict[str, Any]]) -> None:
    """The SSE fallback, for a proxy that eats the upgrade."""
    _send(out, b'data: {"type": "hello"}\n\n')
    while True:
        try:
            message = queue.get(timeout=PING_SECONDS)
        except Empty:
            if not _send(out, b": ping\n\n"):
                return
            continue
        if not _send(out, f"data: {json.dumps(message)}\n\n".encode()):
            return


def _send(out: Writer, payload: bytes) -> bool:
    """A write that fails is a client that left — the only disconnect signal we need."""
    try:
        out.write(payload)
        out.flush()
    except (BrokenPipeError, ConnectionResetError, OSError, ValueError):
        return False
    return True


def attach(out: Responder, hub: Hub, board: str, upgrade: str, key: str) -> None:
    """Answer a GET /feed: WebSocket if the client asked for one, else SSE.

    The subscription is taken BEFORE the first byte goes out and dropped in a
    `finally`, so a client that disappears mid-handshake cannot leave a queue
    behind that the next write would fill forever.
    """
    queue = hub.subscribe(board)
    try:
        if "websocket" in upgrade.lower() and key:
            out.send_response(101)
            out.send_header("Upgrade", "websocket")
            out.send_header("Connection", "Upgrade")
            out.send_header("Sec-WebSocket-Accept", accept_key(key))
            out.end_headers()
            pump_websocket(out.wfile, queue)
        else:
            out.send_response(200)
            out.send_header("Content-Type", "text/event-stream")
            out.send_header("Cache-Control", "no-cache")
            # No Content-Length on a stream, so under HTTP/1.1 the end of this
            # response IS the end of the connection. Say so.
            out.send_header("Connection", "close")
            out.end_headers()
            pump_events(out.wfile, queue)
    finally:
        hub.unsubscribe(board, queue)
