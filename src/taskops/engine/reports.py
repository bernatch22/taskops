"""The fingerprint a written daily report carries, and what makes one STALE.

A dossier on disk is a claim about a day, and the day keeps happening after it is written.
The header line is what lets a reader tell the difference between "this is the day" and
"this was the day as of event 812" — without it, a report generated at noon and read at
midnight is indistinguishable from a complete one, which is the failure mode that makes
generated documents untrustworthy.

`max_seq` and not a timestamp: seq is the log's own local order, so "did anything land
after this was written" is an integer comparison with no clock skew in it. The `generated`
field is for the human, and nothing reads it back.
"""

from __future__ import annotations

import time

from .._types import LOCAL_ONLY_KINDS
from ..storage import Store
from .day import MAX_EVENTS, window

__all__ = ["stamp", "stamped_seq", "missing_events", "NO_STAMP"]

_PREFIX = "<!-- taskops:report"

_FIELD = "max_seq="

NO_STAMP = -1
"""What `stamped_seq` answers for a file nobody generated — a hand-written report, or one
from before this existed. Staleness is then UNKNOWN, and reported as not stale rather than
as stale: nagging about a file taskops did not write is noise nobody can act on."""


def stamp(label: str, max_seq: int, at: float) -> str:
    """The header line. Machine-readable, and an HTML comment so it renders as nothing."""
    return (f"{_PREFIX} date={label} {_FIELD}{max_seq} "
            f"generated={time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(at))} -->")


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


def missing_events(store: Store, from_date: str, to_date: str, since_seq: int) -> int:
    """How many of the window's events landed AFTER the report was generated.

    Scoped to the report's OWN window, because the fingerprint is a global `max_seq`: work on
    another day would otherwise mark every past report stale forever. Heartbeats are
    excluded for the same reason the dossier excludes them — a live agent would make every
    report of today stale within a minute, and the word would stop meaning anything.
    """
    if since_seq <= NO_STAMP:
        return 0
    start, end = window(from_date)[0], window(to_date)[1]
    return sum(1 for event in store.events.after_seq(since_seq, limit=MAX_EVENTS)
               if start <= event["ts"] < end and event["kind"] not in LOCAL_ONLY_KINDS)
