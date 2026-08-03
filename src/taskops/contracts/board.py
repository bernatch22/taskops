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
from .spent import Attended, Stretch
from .task import Task

__all__ = ["Card", "Column", "Board", "Standup", "Burndown", "FleetMember", "Fleet",
           "ActorRoll", "Activity"]


class Card(TypedDict):
    """One task as the board shows it: the row, plus who is on it right now."""

    task: Task
    lease: Lease | None
    blocked_by: int
    blocks: int
    commits: int

    seconds: float
    """How long this card was ATTENDED, summed over every actor that touched it. A floor, and
    `contracts.spent.Attended` is where that word is argued. On the card and not only in a person's
    profile because it is the card's own number: it must not depend on the window somebody happens
    to be reading a profile through, and a card carries it wherever it is drawn."""


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


class ActorRoll(TypedDict):
    """One actor's whole record in the window — what they touched, not whether they are free.

    Availability is not a question worth answering when agents are created on demand: there is no
    pool to allocate from. What survives an agent's session is what it DID, and that is this.
    """

    actor: str
    tasks: int
    """Distinct tasks touched. Deliberately not "events": an actor that commented forty times on
    one card has done less than one that closed four."""

    commits: int
    comments: int
    done: int
    first_seen: float
    last_seen: float

    sittings: list[Stretch]
    """Newest first. What was open at the same time, which no count above can show."""

    on: list[Attended]
    """How long this actor was ON each card, busiest first. See `Attended` for what the number is
    and, more importantly, what it is not."""


class Activity(TypedDict):
    """The event log as something a person can read: a timeline, plus who did what.

    A projection like every other one here — nothing is stored for it. The log already holds every
    fact it shows, which is why this could be added without a migration and why it cannot drift.
    """

    repo: str
    since: float
    events: list[Event]
    """Newest FIRST, unlike the log's own order. A timeline is read from the top, and a reader who
    has to scroll to the bottom to find out what just happened will stop opening it."""

    titles: dict[str, str]
    """Task id -> title, for the tasks these events name. Sent with the timeline rather than fetched
    per row: a hundred events would otherwise be a hundred requests to render one screen."""

    actors: list[ActorRoll]
    kinds: list[str]
    """The kinds actually present, so the filter offers what exists instead of a hardcoded list that
    goes stale the day a new kind is written."""

    truncated: bool


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
