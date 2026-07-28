"""ONE calendar day, in full — what a person reads at the end of it.

A projection like every other one here: nothing is stored for it, every fact comes from
`events.jsonl` plus what git already knows about the commits those events name. That is what
makes it safe to change and what makes it impossible to flatter anybody — a dossier nobody
typed cannot claim a card was closed that the log does not show closed.

The unit is a CALENDAR day and not a rolling window, because that is the question being asked.
"What happened yesterday" and "what happened in the last 24 hours" are different reports, and
the second one silently moves every time it is run.
"""

from __future__ import annotations

from typing import TypedDict

from .board import ActorRoll
from .commit import CommitRef
from .event import Event
from .task import Task

__all__ = ["CommitStat", "ClosedCard", "DayReport"]


class CommitStat(CommitRef):
    """A commit with its SIZE — the one thing the event log does not carry.

    `additions`/`deletions` come from git at read time rather than from the `commit` event,
    because the event is written by a hook that must never be slow and because a diff can be
    recomputed forever while a bad number recorded once is permanent.

    Zeros when git could not answer (no repository, the sha is on another machine, a shallow
    clone). Honest and useless beats raising inside a report.
    """

    additions: int
    deletions: int


class ClosedCard(TypedDict):
    """A card that reached `done` on this day, with everything it took to get there."""

    task: Task
    actor: str
    """Who closed it. The task row keeps the state and never who moved it there — this is the
    only place that fact lives, and it comes from the `done` event."""

    claimed_ts: float
    """When its last claim before the close was taken, or the close itself when the card was
    never claimed (a human closing something by hand). The pair with `done_ts` is the only
    honest duration available: an earlier claim that was released is not time spent."""

    done_ts: float
    commits: list[CommitStat]
    """Every commit bound to the task, not only the ones written today. A card closed at 9am
    after three days of work shipped all of it, and showing one commit would understate it."""


class DayReport(TypedDict):
    """The day, as one object."""

    repo: str
    date: str
    """`YYYY-MM-DD`, in the reader's LOCAL calendar — the window is [00:00, 24:00) of it."""

    closed: list[ClosedCard]
    in_flight: list[Task]
    blocked: list[Task]
    conversations: list[Event]
    actors: list[ActorRoll]
    commits_total: int
