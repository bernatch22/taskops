"""taskops — a shared work board for teams of coding agents.

The public surface is deliberately tiny: open a board, call a verb, handle one
error tree. Everything else (MCP tools, the HTTP server, the git hooks) is a
transport built on top of exactly this.
"""

from __future__ import annotations

from ._errors import (
    Refused,
    NotFound,
    BadRequest,
    Unreachable,
    TaskopsError,
)
from ._version import __version__

__all__ = [
    "TaskopsError",
    "Refused",
    "NotFound",
    "Unreachable",
    "BadRequest",
    "__version__",
]
