"""taskops — the coordination substrate Claude Code does not have.

Persistent tasks with a dependency DAG, atomic claims that survive a crashed
agent, every commit bound to the task that motivated it, and a live board a
human can watch while a hundred agents work.

The error types are exported eagerly because a caller has to be able to write
`except taskops.LeaseHeld` before it has opened anything. Everything else stays
behind its own module so that importing this package costs a dict lookup — the
MCP host imports it to list tools long before it asks for any work.
"""

from __future__ import annotations

from ._errors import (
    AlreadyWritten,
    BadRequest,
    GuardFailed,
    IllegalTransition,
    LeaseHeld,
    NoLease,
    NoSuchTask,
    NotInitialized,
    TaskopsError,
)
from ._version import __version__

__all__ = [
    "__version__",
    "TaskopsError",
    "NotInitialized",
    "NoSuchTask",
    "IllegalTransition",
    "LeaseHeld",
    "NoLease",
    "GuardFailed",
    "BadRequest",
    "AlreadyWritten",
]
