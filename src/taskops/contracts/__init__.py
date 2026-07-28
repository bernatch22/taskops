"""Layer 1 — every payload that crosses a boundary, defined once.

ZERO logic lives here: only types. `storage` reads and writes them, `engine`
decides with them, `render` turns them into text, the three transports serialize
them, and the studio mirrors them in TypeScript. One definition, six readers.

TypedDict on purpose, not dataclasses and not pydantic: at runtime these ARE
dicts, so a consumer writes `task["status"]`, the wire format is the same object
serialized, and the package keeps its zero dependencies.

⚠️ Optionality uses the `total=False` SPLIT, never `NotRequired`. Under
`from __future__ import annotations` every annotation is a string, so TypedDict
cannot see a `NotRequired[...]` marker at class-creation time: `__optional_keys__`
comes back EMPTY and every field reads as required to anything that introspects
the class — including the MCP schema generator, which would then advertise every
optional parameter as mandatory. Totality is class-level, so the split is immune.
`tests/contracts/test_optionality.py` pins this.

This package imports nothing but layer 0, so it can never introduce a cycle —
which is what lets every layer above depend on it freely.
"""

from __future__ import annotations

from .actor import Actor
from .board import (
    Activity,
    ActorRoll,
    Board,
    Burndown,
    Card,
    Column,
    Fleet,
    FleetMember,
    Standup,
)
from .commit import CommitRef
from .dep import Dep
from .event import Event, Inbox
from .gitstate import BranchState
from .lease import Lease
from .log import EntryKind, LogEntry, SessionLog
from .results import Claim, NextResult, PlanResult, UpdateResult
from .task import Task, TaskView
from .tools import AskParams, NextParams, PlanParams, ReportParams, UpdateParams

__all__ = [
    # the entities
    "Task",
    "TaskView",
    "Dep",
    "Lease",
    "Actor",
    "Event",
    "Inbox",
    "BranchState",
    "CommitRef",
    "LogEntry",
    "SessionLog",
    "EntryKind",
    # what the use cases return
    "PlanResult",
    "Claim",
    "NextResult",
    "UpdateResult",
    # the projections
    "Board",
    "Column",
    "Card",
    "Standup",
    "Activity",
    "ActorRoll",
    "Burndown",
    "Fleet",
    "FleetMember",
    # what a tool call carries in
    "PlanParams",
    "NextParams",
    "UpdateParams",
    "AskParams",
    "ReportParams",
]
