"""One calendar day, projected out of the log — the deterministic daily dossier.

Its own module rather than a third window report beside `standup`, because the WINDOW is the
design. A standup asks "what changed in the last 24 hours" and moves every time it is run; this
asks "what happened on Tuesday", and Tuesday is the same tomorrow. That is what makes a day's
report worth writing down and worth diffing against the next one.

Local midnight, not UTC. The reader lives in a timezone and closed a card at 23:50 in it; a UTC
day would file that under the wrong date for everyone west of Greenwich and be defensible only
to the machine.
"""

from __future__ import annotations

import time

from .._errors import BadRequest
from .._types import LOCAL_ONLY_KINDS, WORKING_STATUSES
from ..contracts import DayReport
from ..storage import Store
from ._closed import closed_cards
from .activity import tasks_of
from .history import rolls

__all__ = ["day_report", "window", "date_of", "MAX_EVENTS"]

MAX_EVENTS = 20_000
"""A ceiling, not a page. A day that overflows it is a day nobody could read anyway, and the
alternative — a silent 500-row default — would produce a dossier that looks complete."""


def day_report(store: Store, date: str) -> DayReport:
    """Everything that happened on `date` (`YYYY-MM-DD`), from events and git alone."""
    start, end = window(date)
    events = [e for e in store.events.since(start - 1.0, limit=MAX_EVENTS)
              if start <= e["ts"] < end and e["kind"] not in LOCAL_ONLY_KINDS]
    touched = tasks_of(store, [e["task"] for e in events])
    return DayReport(
        repo=str(store.root), date=date,
        closed=closed_cards(store, [e for e in events if e["kind"] == "done"]),
        in_flight=[t for t in touched if t["status"] in WORKING_STATUSES],
        blocked=[t for t in touched if t["status"] == "blocked"],
        conversations=[e for e in events if e["kind"] in ("comment", "message")],
        actors=rolls(events),
        commits_total=sum(1 for e in events if e["kind"] == "commit"))


def window(date: str) -> tuple[float, float]:
    """`2026-07-28` -> the timestamps of local midnight and the NEXT local midnight.

    Both ends come from `mktime`, which normalises an out-of-range day (`32 July` is
    `1 August`) and applies the zone's own rules — so the day the clocks change is 23 or 25
    hours long here, exactly as it was for the person who worked it. `start + 86400` would
    be wrong twice a year, and wrong in the direction of losing an hour of somebody's work.
    """
    try:
        parsed = time.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise BadRequest(f"`{date}` is not a date — use YYYY-MM-DD, "
                         f"e.g. 2026-07-28") from None
    fields = (parsed.tm_year, parsed.tm_mon, parsed.tm_mday)
    return (_midnight(fields), _midnight((fields[0], fields[1], fields[2] + 1)))


def _midnight(fields: tuple[int, int, int]) -> float:
    """Local 00:00 of a (year, month, day). `-1` for `tm_isdst` lets libc decide, which is
    the only way to get the right answer on the hour a DST transition repeats."""
    year, month, day = fields
    return time.mktime((year, month, day, 0, 0, 0, 0, 0, -1))


def date_of(ts: float) -> str:
    """The local calendar date a timestamp falls on. The inverse of `window`, and what turns
    "now" into a default without a second notion of where a day starts."""
    return time.strftime("%Y-%m-%d", time.localtime(ts))
