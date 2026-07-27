"""The MCP transport: five tools over JSON-RPC on stdio.

Layered on purpose — `tools` is the surface, `schema` generates it from `contracts/`,
`arguments` reads what a model wrote, `dispatch` maps a name to a use case and a renderer,
`protocol` is JSON-RPC as a pure function, and `server` is the wire.

Nothing here imports the engine at module scope: a host lists the tools before it asks
anything, and that handshake must stay free of sqlite and git. `dispatch` is imported inside
`protocol`'s tools/call branch, where the cost is warranted.
"""

from __future__ import annotations

from .protocol import INSTRUCTIONS, PROTOCOL, respond
from .server import main, serve
from .tools import TOOLS, Tool, listing

__all__ = ["TOOLS", "Tool", "listing", "PROTOCOL", "INSTRUCTIONS", "respond",
           "serve", "main"]
