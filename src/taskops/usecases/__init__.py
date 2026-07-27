"""Layer 5 — one module per verb, sync, returning contracts.

Every transport calls THESE, so a behaviour is implemented once and three surfaces
cannot drift apart. `tests/architecture` enforces the other half of that: a transport
may not import `storage` or `engine` directly, which is what stops a fourth place where
a decision lives.

Sync all the way down. taskops is sqlite and a state machine; the http edge may be
async and calls in from a threadpool, but there is no async twin of the engine.
"""

from __future__ import annotations

from ._project import locate
from .ask import ask, search
from .claim import next_task
from .dispatch import DispatchResult, dispatch
from .feed import follow
from .guard import Verdict, check_command, check_commit
from .ingest import ingest_branch, ingest_commit
from .log import session_log
from .plan import plan
from .recover import Recovered, recover
from .report import board, fleet, standup
from .session import Brief, brief, checkout, inbox, track
from .setup import InitReport, init
from .sync import rebuild, sync
from .update import update

__all__ = [
    # the five MCP tools
    "plan", "next_task", "update", "ask", "search", "board", "standup", "fleet",
    "dispatch", "DispatchResult", "recover", "Recovered",
    # the CLI verbs the hooks call
    "init", "InitReport", "check_commit", "check_command", "Verdict",
    "ingest_commit", "ingest_branch",
    "brief", "Brief", "inbox", "checkout", "track", "sync", "rebuild", "follow", "locate", "session_log",
]
