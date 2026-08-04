"""The fingerprint a written daily report carries, and what makes one STALE.

A dossier on disk is a claim about a day, and the day keeps happening after it is written.
The header line is what lets a reader tell the difference between "this is the day" and
"this was the day as of event 812" — without it, a report generated at noon and read at
midnight is indistinguishable from a complete one, which is the failure mode that makes
generated documents untrustworthy.

`max_seq` and not a timestamp: seq is the log's own local order, so "did anything land
after this was written" is an integer comparison with no clock skew in it. The `generated`
field is for the human, and nothing reads it back.

`tz` is the offset the window's midnights were cut at, and it is here because `max_seq` alone
is not enough to order two copies of one day. Two machines five hours apart file the same
events under different dates, so the higher `max_seq` can be the account of a DIFFERENT window
— and "later, therefore fuller" is then false. With the offset on the line, a reader sees it in
one glance and `usecases.reportfile` refuses to let one overwrite the other.
"""

from __future__ import annotations

import time

from .._types import LOCAL_ONLY_KINDS
from ..storage import Store
from .calendar import day_zone, offset_of, window
from .day import MAX_EVENTS

__all__ = ["stamp", "stamp_for", "stamped_seq", "stamped_offset", "missing_events",
           "NO_STAMP", "NO_OFFSET"]

_PREFIX = "<!-- taskops:report"

_FIELD = "max_seq="

_ZONE_FIELD = "tz="

NO_STAMP = -1
"""What `stamped_seq` answers for a file nobody generated — a hand-written report, or one
from before this existed. Staleness is then UNKNOWN, and reported as not stale rather than
as stale: nagging about a file taskops did not write is noise nobody can act on."""

NO_OFFSET = ""
"""What `stamped_offset` answers for a report written before the offset was recorded. Unknown,
never assumed to be ours: every dossier in every repository predates this field, and treating
their silence as agreement would resurrect exactly the overwrite it exists to stop — while
treating it as disagreement would make every one of them unpushable."""


def stamp(label: str, max_seq: int, at: float, offset: str = "") -> str:
    """The header line. Machine-readable, and an HTML comment so it renders as nothing.

    `offset` is the WINDOW's own — see `stamp_for` — and not this moment's. A June day
    regenerated in December is still a June day, and stamping the renderer's current offset
    would make two copies of it look like different windows when they are the same one.
    """
    zone = f" {_ZONE_FIELD}{offset}" if offset else ""
    return (f"{_PREFIX} date={label} {_FIELD}{max_seq}{zone} "
            f"generated={time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(at))} -->")


def stamp_for(store: Store, label: str, start_date: str, at: float) -> str:
    """The header line for a window this project is about to write down.

    Here rather than in the use case that writes the file, because the offset in the stamp has
    to be the one `period_report` actually cut the window with — a second reading of the policy
    at the call site is how a report and its own fingerprint come to describe different days.
    """
    zone = day_zone(store)
    return stamp(label, store.events.max_seq(), at, offset_of(window(start_date, zone)[0], zone))


def stamped_seq(text: str) -> int:
    """The `max_seq` a written report was generated at, or `NO_STAMP`.

    Read off the FIRST line only. A stamp further down is not a stamp — it is prose that
    happens to quote one, and trusting it would let a narration re-date its own report.
    """
    first = text.lstrip().splitlines()[0] if text.strip() else ""
    if not first.startswith(_PREFIX):
        return NO_STAMP
    for field in first.split():
        if field.startswith(_FIELD) and field[len(_FIELD):].isdigit():
            return int(field[len(_FIELD):])
    return NO_STAMP


def stamped_offset(text: str) -> str:
    """The UTC offset a written report's window was cut at, or `NO_OFFSET`.

    First line only, for the same reason `stamped_seq` reads only the first: a stamp quoted in
    prose is prose.
    """
    first = text.lstrip().splitlines()[0] if text.strip() else ""
    if not first.startswith(_PREFIX):
        return NO_OFFSET
    for field in first.split():
        if field.startswith(_ZONE_FIELD):
            return field[len(_ZONE_FIELD):]
    return NO_OFFSET


def missing_events(store: Store, from_date: str, to_date: str, since_seq: int) -> int:
    """How many of the window's events landed AFTER the report was generated.

    Scoped to the report's OWN window, because the fingerprint is a global `max_seq`: work on
    another day would otherwise mark every past report stale forever. Heartbeats are
    excluded for the same reason the dossier excludes them — a live agent would make every
    report of today stale within a minute, and the word would stop meaning anything.
    """
    if since_seq <= NO_STAMP:
        return 0
    zone = day_zone(store)
    start, end = window(from_date, zone)[0], window(to_date, zone)[1]
    return sum(1 for event in store.events.after_seq(since_seq, limit=MAX_EVENTS)
               if start <= event["ts"] < end and event["kind"] not in LOCAL_ONLY_KINDS)
