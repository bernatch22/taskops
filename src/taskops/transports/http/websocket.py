"""The websocket handshake: turning an HTTP request into a socket.

Only the upgrade lives here. Everything that flows afterwards is `_wsframes`, and the split is the
same one the rest of this package makes everywhere — HTTP is one concern, the binary protocol on the
other side of it is another.
"""

from __future__ import annotations

import base64
import hashlib
import os

from ._wsframes import (
    OPCODE_CLOSE,
    OPCODE_PING,
    OPCODE_PONG,
    OPCODE_TEXT,
    close_frame,
    ping_frame,
    read_frame,
    text_frame,
)

__all__ = ["accept_key", "handshake_headers", "is_upgrade", "new_key", "text_frame",
           "close_frame", "ping_frame", "read_frame", "OPCODE_TEXT", "OPCODE_CLOSE",
           "OPCODE_PING", "OPCODE_PONG"]

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
"""The magic string from RFC 6455 §4.2.2. It exists so a server cannot accidentally complete a
handshake it did not understand — the client checks that we hashed its key with exactly this."""


def is_upgrade(headers: dict[str, str]) -> bool:
    """Is this request asking to become a websocket.

    Checked on the lower-cased header map the server already built. `Connection` may legitimately be
    a LIST (`keep-alive, Upgrade`), which is why this is a substring test and not equality — the
    equality version works in every browser and fails behind some proxies.
    """
    return ("websocket" in headers.get("upgrade", "").lower()
            and "upgrade" in headers.get("connection", "").lower()
            and bool(headers.get("sec-websocket-key")))


def accept_key(client_key: str) -> str:
    """The `Sec-WebSocket-Accept` value: sha1 of the key plus the GUID, base64."""
    digest = hashlib.sha1((client_key.strip() + _GUID).encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


def handshake_headers(client_key: str) -> dict[str, str]:
    """The headers that complete the upgrade. Status 101 is the server's job."""
    return {"Upgrade": "websocket", "Connection": "Upgrade",
            "Sec-WebSocket-Accept": accept_key(client_key)}


def new_key() -> str:
    """A client-side `Sec-WebSocket-Key`. Only the tests need this — a browser makes its own."""
    return base64.b64encode(os.urandom(16)).decode("ascii")
