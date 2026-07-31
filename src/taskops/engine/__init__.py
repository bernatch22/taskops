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
from ._acceptance import Evidence, evidenced
from .activity import fleet, standup
from .attention import waiting_on
from .bus import BUS, EventBus
from .day import date_of, day_report, first_date, label_of, period_report, shift
from .gitstate import branch_state, branch_states
from .history import activity
from .identity import parse, resolve
from .log import build, record, relay
from .machine import Facts, allowed_from, check_move
from .narrate import OnPass, OnText, narrate
from .project import board, counts
from .reports import NO_STAMP, missing_events, stamp, stamped_seq
from .scheduler import branch_for, claim, hand_back, open_children, ready_tasks, sweep_dead, unblock
from .team import team
from .wire import WIRE, Broadcast, is_wire
from .worker import Launched

__all__ = ["Facts", "Evidence", "evidenced", "check_move", "allowed_from", "resolve", "parse", "record",
           "build", "relay", "BUS", "EventBus", "unblock", "hand_back", "ready_tasks", "claim",
           "branch_for", "sweep_dead", "open_children", "board", "standup", "waiting_on",
    "team", "fleet", "activity", "day_report", "period_report", "first_date", "label_of", "shift", "date_of",
           "counts", "replay", "narrate", "OnPass", "OnText", "stamp", "stamped_seq", "NO_STAMP", "missing_events", "branch_state", "branch_states", "Launched", "WIRE", "Broadcast", "is_wire"]
