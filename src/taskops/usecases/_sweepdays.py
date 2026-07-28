"""Which days a sweep owes prose to — the barrier's condition, computed and nothing else.

Kept apart from the run loop because it is the half that must be provably cheap and provably
pure: it opens the store, reads, and answers a list. Every question about "did this day get
narrated" is settled HERE, so the loop below it never has to second-guess a day it was given.

The candidates come from the LOG, never from `.taskops/reports/`. A directory listing answers
"which reports exist", and a day whose file somebody deleted would then be a day that never
happened — the exact opposite of what a backfill is for.
"""

from __future__ import annotations

from pathlib import Path

from .._types import LOCAL_ONLY_KINDS
from ..contracts import ReportEntry
from ..engine import date_of
from ..engine.day import MAX_EVENTS
from ..storage import Store
from ._project import project
from .index import report_index

__all__ = ["pending_days"]


def pending_days(start: Path | str, today: str) -> list[str]:
    """Every ENDED day with events and no usable narration, oldest first.

    Oldest first so a machine that was away a week fills the hole in the order the week
    happened: a reader who opens the reports directory afterwards finds a run of days, not a
    fortnight with Thursday in the middle of it.

    `today` is dropped whatever the clock says. A day is not narrated until it has ended, and
    narrating it at 3pm produces a document that claims to be the day and is missing its
    evening — permanently, because the next sweep sees a report that already carries prose.
    """
    with project(start) as store:
        days = _days_with_events(store)
    written = {entry["label"]: entry for entry in report_index(start)}
    return [day for day in days if day < today and _unfinished(written.get(day))]


def _days_with_events(store: Store) -> list[str]:
    """The local dates the log actually touches, sorted.

    Heartbeats are excluded for the same reason the dossier excludes them: an agent left
    running overnight would mint a calendar day whose report has nothing in it, and a sweep
    would then pay a model to say so.
    """
    seen = {date_of(event["ts"]) for event in store.events.since(-1.0, limit=MAX_EVENTS)
            if event["kind"] not in LOCAL_ONLY_KINDS}
    return sorted(seen)


def _unfinished(entry: ReportEntry | None) -> bool:
    """A day is owed prose when nobody wrote it up, or when the write happened too early.

    `missing_events` is the second half and the one that is easy to forget: a report generated
    at 18:00 and narrated then is a complete-looking document about a day that kept going.
    Re-narrating it is cheap; a permanent half-day is not.

    A report narrated on ANOTHER machine and pulled down passes this test unchanged — it is a
    file with prose in it, and where the prose came from was never part of the question.
    """
    return entry is None or not entry["has_narration"] or entry["missing_events"] > 0
