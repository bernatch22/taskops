"""The projections — what a human or an agent gets to LOOK at.

Every one of these is derived from tasks plus the event log, never stored. That is
the property that makes them safe to change: a new column or a different standup
window is a rendering decision, not a migration.
"""

from __future__ import annotations

from typing import TypedDict

from .._types import Status
from .event import Event
from .gitstate import BranchState
from .lease import Lease
from .task import Task

__all__ = ["Card", "Column", "Board", "Standup", "Burndown", "FleetMember", "Fleet"]


class Card(TypedDict):
    """One task as the board shows it: the row, plus who is on it right now."""

    task: Task
    lease: Lease | None
    blocked_by: int
    blocks: int
    commits: int


class Column(TypedDict):
    status: Status
    cards: list[Card]


class Board(TypedDict):
    """The whole project, column by column, in declaration order of `STATUSES`."""

    repo: str
    columns: list[Column]
    ready: int
    """How many tasks could be picked up this second. The one number that says
    whether adding another agent would help or just add contention."""

    total: int


class Standup(TypedDict):
    """What happened in a window, per actor — generated, never written by hand."""

    repo: str
    since: float
    actors: list[str]
    events: list[Event]
    done: list[Task]
    in_flight: list[Task]
    blocked: list[Task]


class Burndown(TypedDict):
    """Open versus closed over time. Deliberately coarse: a day-level series is
    what a burndown IS, and anything finer is a live board's job."""

    repo: str
    days: list[str]
    open_counts: list[int]
    done_counts: list[int]


class FleetMember(TypedDict):
    """One live session, as the fleet view sees it."""

    actor: str
    session: str
    task: str
    branch: str
    alive: bool
    """False once the lease has gone quiet past its grace — the lease is still on
    the books, so the board must be able to show a claim it no longer believes."""

    last_seen: float
    doing: str
    """The most recent `activity` event's summary — what tool touched what file.
    Empty when the agent has not reported any, which a session without the plugin
    installed never will."""

    git: BranchState
    """Whether this agent's work is reachable by anybody else yet.

    The question a standup actually asks. An agent can be busy, alive, and holding three unpushed
    commits that exist on one laptop — which looks identical to progress on a board that only shows
    activity."""


class Fleet(TypedDict):
    repo: str
    members: list[FleetMember]
