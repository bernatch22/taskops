"""Constructing the server. The handler itself is `_handler`.

`ThreadingHTTPServer` and not asyncio: the engine is synchronous by an enforced invariant, and a
thread per connection is what lets a live websocket or SSE stream park in a generator without the
sqlite underneath ever learning about it. A handful of threads for a handful of tabs is the right
size — this is a local tool, not a service.
"""

from __future__ import annotations

from http.server import ThreadingHTTPServer
from pathlib import Path

from ._handler import Handler
from .policy import Policy
from .router import build

__all__ = ["build_server", "bound_port"]


def build_server(host: str, port: int, root: Path, policy: Policy) -> ThreadingHTTPServer:
    """A server ready to `serve_forever`. Returned rather than run, so a test can bind port 0.

    The route table is bound into a per-server handler SUBCLASS, because stdlib's server takes a
    class and instantiates it per request — there is nowhere else to put the root and the policy
    without making them module state, which two servers in one process (every test file here) would
    then share.
    """
    route = build(root, policy)

    class Bound(Handler):
        dispatch = staticmethod(route)

    server = ThreadingHTTPServer((host, port), Bound)
    server.daemon_threads = True
    return server


def bound_port(server: ThreadingHTTPServer) -> int:
    """The port actually bound. With `--port 0` the OS chooses, and this is how it gets said."""
    return int(server.socket.getsockname()[1])
