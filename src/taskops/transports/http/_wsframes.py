"""RFC 6455 framing: bytes in, bytes out. No HTTP, no sockets, no state.

Split from `websocket` by concern — that module turns an HTTP request into a socket, this one is the
binary protocol that flows afterwards. Pure functions over bytes, so every boundary condition below
is testable from a literal.

Hand-rolled rather than taking the `websockets` library, and the reason is architectural: that
library is asyncio, and this engine is synchronous by an enforced invariant. Adopting it would mean
an event loop, a threadpool bridge, and a second concurrency model inside a package whose whole
storage story is "sqlite, synchronously" — and it would be the first runtime dependency in a package
that installs into every agent's environment on every machine.

What is deliberately NOT here: outgoing fragmentation (taskops frames are a few hundred bytes),
extensions, and `permessage-deflate`.
"""

from __future__ import annotations

import struct
from typing import BinaryIO

__all__ = ["text_frame", "close_frame", "ping_frame", "read_frame",
           "OPCODE_TEXT", "OPCODE_CLOSE", "OPCODE_PING", "OPCODE_PONG"]

OPCODE_TEXT = 0x1
OPCODE_CLOSE = 0x8
OPCODE_PING = 0x9
OPCODE_PONG = 0xA

_MAX_PAYLOAD = 1 << 20
"""1 MB per incoming frame. The client only ever sends pings and closes here, so anything large is a
mistake or a probe — and reading a declared length into memory before checking it is the classic way
a small server becomes a denial-of-service target."""

def text_frame(payload: str) -> bytes:
    """One unfragmented text frame, unmasked.

    A server MUST NOT mask (RFC 6455 §5.1) — a masked server frame is a protocol error and browsers
    close the connection on it, which reads as a mysteriously dropped socket.
    """
    body = payload.encode("utf-8")
    return _header(OPCODE_TEXT, len(body)) + body


def close_frame(code: int = 1000) -> bytes:
    """A clean close. Sending one before hanging up is what makes the browser's `onclose` carry a
    normal code instead of 1006, which is the code that means "we have no idea what happened"."""
    return _header(OPCODE_CLOSE, 2) + struct.pack("!H", code)


def ping_frame() -> bytes:
    """An empty ping. The protocol's OWN liveness probe, and unlike a comment on an SSE stream it
    gets an answer — so a browser can tell a live-but-idle board from a dead socket."""
    return _header(OPCODE_PING, 0)


def _header(opcode: int, length: int) -> bytes:
    """FIN set, no mask, and the three length encodings RFC 6455 defines.

    The boundaries are exact and unforgiving: 125 inclusive for the short form, 126 as the marker for
    a 16-bit length, 127 for 64-bit. An off-by-one here produces a frame a browser silently discards.
    """
    first = 0x80 | opcode
    if length < 126:
        return struct.pack("!BB", first, length)
    if length < (1 << 16):
        return struct.pack("!BBH", first, 126, length)
    return struct.pack("!BBQ", first, 127, length)


def read_frame(stream: BinaryIO) -> tuple[int, bytes] | None:
    """One incoming frame as `(opcode, payload)`, or None when the stream ends.

    Client frames are always masked, and the mask is applied by XOR with a repeating 4-byte key.
    Unmasking is not optional: without it a ping's payload comes back as noise and the pong we send
    would not match, which some clients treat as a failed connection.
    """
    head = _exactly(stream, 2)
    if head is None:
        return None
    opcode = head[0] & 0x0F
    masked = bool(head[1] & 0x80)
    length = head[1] & 0x7F
    if length == 126:
        extended = _exactly(stream, 2)
        length = struct.unpack("!H", extended)[0] if extended else 0
    elif length == 127:
        extended = _exactly(stream, 8)
        length = struct.unpack("!Q", extended)[0] if extended else 0
    if length > _MAX_PAYLOAD:
        return OPCODE_CLOSE, b""
    mask = _exactly(stream, 4) if masked else b""
    payload = _exactly(stream, length) if length else b""
    if payload is None or (masked and mask is None):
        return None
    return opcode, _unmask(payload, mask) if masked and mask else payload


def _unmask(payload: bytes, mask: bytes) -> bytes:
    return bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))


def _exactly(stream: BinaryIO, count: int) -> bytes | None:
    """Read exactly `count` bytes, or None if the stream ended first.

    A loop rather than one `read(count)`: a socket read is allowed to return fewer bytes than asked
    for, and treating a short read as a complete frame is the bug that makes a websocket work
    perfectly on localhost and corrupt frames over a real network.
    """
    out = b""
    while len(out) < count:
        chunk = stream.read(count - len(out))
        if not chunk:
            return None
        out += chunk
    return out
