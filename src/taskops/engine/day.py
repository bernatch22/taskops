"""A span of calendar days, projected out of the log — the deterministic dossier.

Its own module rather than a third window report beside `standup`, because the WINDOW is the
design. A standup asks "what changed in the last 24 hours" and moves every time it is run; this
asks "what happened on Tuesday", or "what happened in July", and July is the same tomorrow.
That is what makes this report worth writing down and worth diffing against the next one.

A day is the SMALLEST case, not the only one. "How did the project go" is not a question about
Tuesday, and answering it by reading thirty daily files is how nobody answers it — so the same
assembly runs over any span of whole days, ending at a midnight the reader would recognise.

Where the day is CUT lives in `calendar` — local midnight by default, the project's `day_zone`
when a shared board has settled whose midnight it is. Every window here goes through it, and
nothing here computes a boundary of its own.
"""

from __future__ import annotations

from .._clock import now
from .._errors import BadRequest
from .._types import LOCAL_ONLY_KINDS, WORKING_STATUSES
from ..contracts import PeriodReport
from ..storage import Store
from ._closed import closed_cards
from ._opened import opened_cards, waiting_tasks
from .activity import tasks_of
from .calendar import date_of, day_zone, window
from .history import rolls

__all__ = ["period_report", "day_report", "label_of", "first_date", "MAX_EVENTS", "MAX_CLOSED"]

MAX_EVENTS = 20_000
"""A ceiling, not a page. A day that overflows it is a day nobody could read anyway, and the
alternative — a silent 500-row default — would produce a dossier that looks complete."""

MAX_CLOSED = 200
"""How many closed cards one report renders in full. A month can close more than a person
will read, and every card carries its whole commit list — so the cap is real. What is NOT
allowed is cutting quietly: the overflow is counted into `dropped` and printed."""


def day_report(store: Store, date: str) -> PeriodReport:
    """Everything that happened on `date` (`YYYY-MM-DD`) — the one-day case of a period."""
    return period_report(store, date, date)


def period_report(store: Store, start_date: str, end_date: str,
                  label: str = "") -> PeriodReport:
    """Every day from `start_date` to `end_date` INCLUSIVE, from events and git alone.

    One assembly, not two: a week is a day with a wider window, and a second copy of this
    would be the copy that forgets to exclude heartbeats.

    `label` is an override for the one name the dates cannot produce: `report all` covers a
    span that is only incidentally 2026-07-14..2026-07-28, and calling its file that would
    mean yesterday's "everything" and today's are two different documents.
    """
    zone = day_zone(store)
    start, end = window(start_date, zone)[0], window(end_date, zone)[1]
    if end <= start:
        raise BadRequest(f"`{start_date}` is after `{end_date}` — a range runs forwards")
    events = [e for e in store.events.since(start - 1.0, limit=MAX_EVENTS)
              if start <= e["ts"] < end and e["kind"] not in LOCAL_ONLY_KINDS]
    touched = tasks_of(store, [e["task"] for e in events])
    dones = [e for e in events if e["kind"] == "done"]
    opened = opened_cards(store, events)
    return PeriodReport(
        repo=str(store.root), from_date=start_date, to_date=end_date,
        label=label or label_of(start_date, end_date),
        closed=closed_cards(store, dones[-MAX_CLOSED:]),
        dropped=max(0, len(dones) - MAX_CLOSED),
        opened=opened,
        in_flight=[t for t in touched if t["status"] in WORKING_STATUSES],
        blocked=[t for t in touched if t["status"] == "blocked"],
        waiting=waiting_tasks(touched, opened),
        conversations=[e for e in events if e["kind"] in ("comment", "message")],
        actors=rolls(events),
        commits_total=sum(1 for e in events if e["kind"] == "commit"))


def label_of(start_date: str, end_date: str) -> str:
    """`2026-07-28` for one day, `2026-07-22..2026-07-28` for a range.

    Derived in ONE place because it is both the report's heading and the name of the file it
    is written to — computing it twice is how a `2026-07-22..28.md` ends up titled otherwise.
    """
    return start_date if start_date == end_date else f"{start_date}..{end_date}"


def first_date(store: Store) -> str:
    """The local date of the OLDEST event in the log — where `report all` starts.

    Read from the log rather than from the repository's first commit: taskops knows about the
    project from its first event, and claiming to cover days that predate the log would be
    reporting silence as a fact.
    """
    oldest = store.events.since(-1.0, limit=1)
    return date_of(oldest[0]["ts"]) if oldest else date_of(now())
