"""The HTTP transport: the studio's UI and its JSON API on one port.

Layered like the MCP one and for the same reasons — `_wire` is the request/reply shape, `policy`
is who may do what, `api` is the endpoints, `live` is the SSE feed, `static` serves the built
bundle, `router` maps a path to one of them, and `server` is the only file that knows about HTTP.

This is the one place the codebase is allowed to be async-adjacent, and it is not: it uses threads
(`ThreadingHTTPServer`), which is what lets a live browser park in a generator while the sync
engine underneath stays sync. See `live` for why the feed is SSE rather than a WebSocket.
"""

from __future__ import annotations

from .policy import Policy
from .server import bound_port, build_server

__all__ = ["Policy", "build_server", "bound_port"]
