"""Where a day STARTS — the one decision every window report is built on.

Split from `day` because it is not the projection, it is the ruler the projection measures with,
and two things wanted it at once: the dossier's window and the stamp that records which window
was cut. A copy of `mktime((y, m, d, 0, 0, 0, 0, 0, -1))` in the second caller is how a report
and its own fingerprint end up describing different days.

**Local midnight, not UTC.** The reader lives in a timezone and closed a card at 23:50 in it; a
UTC day would file that under the wrong date for everyone west of Greenwich and be defensible
only to the machine.

**Local, that is, until a project says otherwise — and a shared board has to.** "The reader's
zone" is one zone while one machine renders. Two developers three hours apart file the same
events under different dates, so they render one closed day into two different documents, and a
dossier is a FILE: the second one replaces the first with no conflict to see. Measured on the
axion board, 2026-07-30 counted 8 commits and 5 opened cards generated at UTC-3 and 5 commits
and 3 cards at UTC+2 — the other three commits sitting inside 07-31, nothing lost and nothing
agreeing either. So the boundary is a project POLICY (`day_zone`), unset by default, which
leaves the single-machine case byte-for-byte as it was, and the offset it produced is written
into the report's stamp: a window nobody can name is a window a reader cannot check.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .._errors import BadRequest
from ..storage import Store
from ..storage.policy import in_force

__all__ = ["day_zone", "window", "offset_of", "shift", "date_of"]


def day_zone(store: Store) -> str:
    """The zone this PROJECT cuts its days in, or "" for the machine's own.

    A setting and not a constant because the answer is a decision about a TEAM: one machine has
    no disagreement to settle, and a board two developers render from has nothing else that can
    settle it. Read on every report rather than cached — it is a fold over a handful of events,
    and a zone read once at import is a report that moves after somebody sets it.
    """
    return in_force(store, "day_zone")


def window(date: str, zone: str = "") -> tuple[float, float]:
    """`2026-07-28` -> the timestamps of that day's midnight and the NEXT midnight.

    Both ends come from the same calendar arithmetic, which applies the zone's own rules — so
    the day the clocks change is 23 or 25 hours long here, exactly as it was for the person who
    worked it. `start + 86400` would be wrong twice a year, and wrong in the direction of losing
    an hour of somebody's work.

    `zone` empty is the machine's own, which is what every caller with no project to ask gets.
    A named zone makes the interval the SAME on every machine, and that is the only way two
    developers' dossiers of one day can be the same document.
    """
    fields = _fields(date)
    return (_midnight(fields, zone), _midnight((fields[0], fields[1], fields[2] + 1), zone))


def offset_of(ts: float, zone: str = "") -> str:
    """The UTC offset a window's midnight was cut at, as `+0200` — what the stamp records.

    The OFFSET and not the zone's name: two machines agree about a day exactly when their
    midnights coincide, so `Europe/Madrid` and `Africa/Ceuta` are the same window while
    `Europe/Madrid` in July and in January are not. What a reader compares is the number that
    decided the cut.
    """
    if not zone:
        return time.strftime("%z", time.localtime(ts))
    return datetime.fromtimestamp(ts, _tz(zone)).strftime("%z")


def shift(date: str, *, days: int = 0, months: int = 0) -> str:
    """`2026-07-28`, `days=-6` -> `2026-07-22`. What turns `--last 7d` into a start date.

    The calendar normalises an out-of-range field, so `months=-1` on the 31st of a month with no
    31st lands on the 1st or the 3rd of the next one rather than raising. Approximate at the
    edges and never wrong about how long a month is, which is the trade a hand-rolled
    `date - 30` gets backwards.
    """
    year, month, day = _fields(date)
    return date_of(_midnight((year, month + months, day + days)))


def date_of(ts: float, zone: str = "") -> str:
    """The calendar date a timestamp falls on. The inverse of `window`, and what turns "now"
    into a default without a second notion of where a day starts."""
    if not zone:
        return time.strftime("%Y-%m-%d", time.localtime(ts))
    return datetime.fromtimestamp(ts, _tz(zone)).strftime("%Y-%m-%d")


def _fields(date: str) -> tuple[int, int, int]:
    """`2026-07-28` -> (2026, 7, 28), refused with the shape it wanted if it is not a date."""
    try:
        parsed = time.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise BadRequest(f"`{date}` is not a date — use YYYY-MM-DD, "
                         f"e.g. 2026-07-28") from None
    return (parsed.tm_year, parsed.tm_mon, parsed.tm_mday)


def _midnight(fields: tuple[int, int, int], zone: str = "") -> float:
    """00:00 of a (year, month, day). `-1` for `tm_isdst` lets libc decide, which is the only
    way to get the right answer on the hour a DST transition repeats.

    Out-of-range fields NORMALISE, in both branches: this is called with `day + 1` to find the
    end of a month's last day and with `month ± n` by `shift`, so arithmetic that raised on
    `32 July` would break its callers rather than the input. `timedelta` on a naive date does
    for a named zone what `mktime` does for the machine's.
    """
    year, month, day = fields
    if not zone:
        return time.mktime((year, month, day, 0, 0, 0, 0, 0, -1))
    year, month = year + (month - 1) // 12, (month - 1) % 12 + 1
    return (datetime(year, month, 1) + timedelta(days=day - 1)
            ).replace(tzinfo=_tz(zone)).timestamp()


def _tz(zone: str) -> ZoneInfo:
    """The zone, or a refusal naming it. Validated at the door by `usecases.policy`; this is the
    second line of defence, for a value that reached the log from a newer taskops or from a
    machine whose tz database does not carry it."""
    try:
        return ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        raise BadRequest(f"`{zone}` is not a timezone this machine knows — "
                         f"`taskops policy day_zone <IANA zone>`, e.g. Europe/Madrid") from None
