"""Layer 3 — the decisions. Sync, and it never talks to a caller.

Split from `usecases` by WHO it is for: these functions decide things (may this move
happen, which task is next, is that agent alive), and a use case orchestrates them
into an answer a transport can render. That is why nothing here formats text and
nothing here reads an argument a model wrote.

`machine` is the only module allowed to decide a status move — `tests/architecture`
enforces it — because a transition table plus one convenient status check elsewhere
is two state machines, and the convenient one always forgets the guard.
"""

from __future__ import annotations

from . import replay
from .activity import fleet, standup
from .bus import BUS, EventBus
from .day import date_of, day_report
from .gitstate import branch_state, branch_states
from .history import activity
from .identity import parse, resolve
from .log import build, record, relay
from .machine import Facts, allowed_from, check_move
from .narrate import narrate
from .project import board, counts
from .reports import missing_events, stamp, stamped_seq
from .scheduler import branch_for, claim, open_children, ready_tasks, sweep_dead, unblock
from .worker import Launched, launch

__all__ = ["Facts", "check_move", "allowed_from", "resolve", "parse", "record",
           "build", "relay", "BUS", "EventBus", "unblock", "ready_tasks", "claim",
           "branch_for", "sweep_dead", "open_children", "board", "standup", "fleet", "activity", "day_report", "date_of",
           "counts", "replay", "narrate", "stamp", "stamped_seq", "missing_events", "branch_state", "branch_states", "launch", "Launched"]
