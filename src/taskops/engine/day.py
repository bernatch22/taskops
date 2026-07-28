"""A span of calendar days, projected out of the log — the deterministic dossier.

Its own module rather than a third window report beside `standup`, because the WINDOW is the
design. A standup asks "what changed in the last 24 hours" and moves every time it is run; this
asks "what happened on Tuesday", or "what happened in July", and July is the same tomorrow.
That is what makes this report worth writing down and worth diffing against the next one.

A day is the SMALLEST case, not the only one. "How did the project go" is not a question about
Tuesday, and answering it by reading thirty daily files is how nobody answers it — so the same
assembly runs over any span of whole days, ending at a midnight the reader would recognise.

Local midnight, not UTC. The reader lives in a timezone and closed a card at 23:50 in it; a UTC
day would file that under the wrong date for everyone west of Greenwich and be defensible only
to the machine.
"""

from __future__ import annotations

import time

from .._clock import now
from .._errors import BadRequest
from .._types import LOCAL_ONLY_KINDS, WORKING_STATUSES
from ..contracts import PeriodReport
from ..storage import Store
from ._closed import closed_cards
from .activity import tasks_of
from .history import rolls

__all__ = ["period_report", "day_report", "label_of", "first_date", "window", "shift",
           "date_of", "MAX_EVENTS", "MAX_CLOSED"]

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
    start, end = window(start_date)[0], window(end_date)[1]
    if end <= start:
        raise BadRequest(f"`{start_date}` is after `{end_date}` — a range runs forwards")
    events = [e for e in store.events.since(start - 1.0, limit=MAX_EVENTS)
              if start <= e["ts"] < end and e["kind"] not in LOCAL_ONLY_KINDS]
    touched = tasks_of(store, [e["task"] for e in events])
    dones = [e for e in events if e["kind"] == "done"]
    return PeriodReport(
        repo=str(store.root), from_date=start_date, to_date=end_date,
        label=label or label_of(start_date, end_date),
        closed=closed_cards(store, dones[-MAX_CLOSED:]),
        dropped=max(0, len(dones) - MAX_CLOSED),
        in_flight=[t for t in touched if t["status"] in WORKING_STATUSES],
        blocked=[t for t in touched if t["status"] == "blocked"],
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


def shift(date: str, *, days: int = 0, months: int = 0) -> str:
    """`2026-07-28`, `days=-6` -> `2026-07-22`. What turns `--last 7d` into a start date.

    `mktime` does the calendar: an out-of-range field is normalised, so `months=-1` on the
    31st of a month with no 31st lands on the 1st or the 3rd of the next one rather than
    raising. Approximate at the edges and never wrong about how long a month is, which is the
    trade a hand-rolled `date - 30` gets backwards.
    """
    parsed = time.strptime(date, "%Y-%m-%d")
    return date_of(_midnight((parsed.tm_year, parsed.tm_mon + months,
                              parsed.tm_mday + days)))


def _midnight(fields: tuple[int, int, int]) -> float:
    """Local 00:00 of a (year, month, day). `-1` for `tm_isdst` lets libc decide, which is
    the only way to get the right answer on the hour a DST transition repeats."""
    year, month, day = fields
    return time.mktime((year, month, day, 0, 0, 0, 0, 0, -1))


def date_of(ts: float) -> str:
    """The local calendar date a timestamp falls on. The inverse of `window`, and what turns
    "now" into a default without a second notion of where a day starts."""
    return time.strftime("%Y-%m-%d", time.localtime(ts))
