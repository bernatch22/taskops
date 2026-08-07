"""Time spent, and the calendar windows to report it over.

Two pieces of arithmetic bought with blood in v1:

* **A gap longer than GAP is DROPPED, not capped.** v1 capped it at 30 min and
  every session break added a phantom half hour; totals ran ahead of reality
  by exactly 30m x breaks (fixed in v1 commit 72550c2). Dropping is the honest
  answer: nobody knows what happened in that hour.
* **Calendar windows use both midnights of the same computation**, never
  `start + 86400`. A DST day is 23 or 25 hours long and adding a constant
  silently shifts every subsequent day of the report.

The signal is the timestamp of the events themselves. In v1 it was `activity`
events that were local-only and never reached the server, so hours were
systematically low and irreproducible after a rebuild.
"""

from __future__ import annotations

from typing import Sequence
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

GAP = 30 * 60.0


def spent(stamps: Sequence[tuple[float, str]]) -> dict[str, float]:
    """Seconds per card, from one actor's timestamped events.

    Each interval is credited to the card of the event that CLOSES it — once.
    Intervals longer than GAP are dropped whole.
    """
    totals: dict[str, float] = {}
    ordered = sorted(stamps)
    for (before, _), (after, task) in zip(ordered, ordered[1:], strict=False):
        delta = after - before
        if 0 < delta <= GAP:
            totals[task] = totals.get(task, 0.0) + delta
    return totals


def total(stamps: Sequence[tuple[float, str]]) -> float:
    return sum(spent(stamps).values())


def day_bounds(when: float, tz: str) -> tuple[float, float]:
    """[local midnight, next local midnight) around `when`, DST-correct."""
    zone = ZoneInfo(tz)
    local = datetime.fromtimestamp(when, zone)
    return _midnights(local.date(), zone)


def windows(now: float, tz: str, days: int) -> list[tuple[str, float, float]]:
    """The last `days` calendar days, oldest first: (YYYY-MM-DD, start, end)."""
    zone = ZoneInfo(tz)
    today = datetime.fromtimestamp(now, zone).date()
    out: list[tuple[str, float, float]] = []
    for back in range(days - 1, -1, -1):
        day = today - timedelta(days=back)
        start, end = _midnights(day, zone)
        out.append((day.isoformat(), start, end))
    return out


def _midnights(day: date, zone: ZoneInfo) -> tuple[float, float]:
    start = datetime(day.year, day.month, day.day, tzinfo=zone)
    nxt = day + timedelta(days=1)
    end = datetime(nxt.year, nxt.month, nxt.day, tzinfo=zone)
    return start.timestamp(), end.timestamp()


def human(seconds: float) -> str:
    """`2h 40m` / `35m` / `—`. One formatter, used by every reader."""
    minutes = int(seconds // 60)
    if minutes <= 0:
        return "—"
    hours, rest = divmod(minutes, 60)
    if hours and rest:
        return f"{hours}h {rest}m"
    return f"{hours}h" if hours else f"{rest}m"
