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

__all__ = ["CommitStat", "ClosedCard", "PeriodReport", "DayReport", "ReportFile"]


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


class PeriodReport(TypedDict):
    """A WINDOW of calendar days, as one object. One day is the case where both ends match.

    ONE contract rather than a day report and a range report side by side: they carry exactly
    the same facts over a wider window, and two shapes would drift the moment a field was
    added to the one somebody happened to be reading.
    """

    repo: str
    from_date: str
    """`YYYY-MM-DD`, in the reader's LOCAL calendar. The window opens at its 00:00."""

    to_date: str
    """`YYYY-MM-DD`, INCLUSIVE — the window closes at the midnight AFTER it."""

    label: str
    """What a human calls this window, and what names its file: `2026-07-28` for one day,
    `2026-07-22..2026-07-28` for a range, `all` for the whole project. Derived and never
    typed, so the heading of a report and the name of the file on disk cannot disagree."""

    closed: list[ClosedCard]
    dropped: int
    """Closed cards the window held and this report does NOT carry, because the cap cut them.

    Reported rather than silent, exactly as the activity view reports truncation: a month
    that closed 400 cards and shows 200 of them is a fine report and a terrible lie."""

    in_flight: list[Task]
    blocked: list[Task]
    conversations: list[Event]
    actors: list[ActorRoll]
    commits_total: int


DayReport = PeriodReport
"""The one-day case, under the name every caller already used. An alias and not a second
TypedDict — a subclass would be a second shape to keep in step for no gain."""


class ReportFile(TypedDict):
    """A day's dossier as it exists ON DISK — or as it would be if it were written.

    `exists` and `stale` are two different answers and both are needed: a day nobody wrote up
    is not the same as one written before half of it happened, and a reader who cannot tell
    them apart will either regenerate a report somebody narrated or cite one that is short.
    """

    date: str
    path: str
    dossier_md: str
    """The written file when there is one, INCLUDING any narration; otherwise the dossier the
    generator would produce right now. A caller always gets something to read."""

    exists: bool
    stale: bool
    missing_events: int
    """How many of the day's events landed after the file was generated. `stale` is this
    being non-zero; the number is here so a UI can say how far behind rather than just that
    it is."""
