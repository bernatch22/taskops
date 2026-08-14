"""Time spent, and the calendar windows to report it over.

Two pieces of arithmetic bought with blood in v1:

* **A gap longer than GAP is DROPPED, not capped.** v1 capped it at 30 min and
  every session break added a phantom half hour; totals ran ahead of reality
  by exactly 30m x breaks (fixed in v1 commit 72550c2). Dropping is the honest
  answer: nobody knows what happened in that hour.
* **Calendar windows use both midnights of the same computation**, never
  `start + 86400`. A DST day is 23 or 25 hours long and adding a constant
  silently shifts every subsequent day of the report.
* **An interval belongs to the window its CLOSING stamp is in** (`since=`).
  v2 handed `sessions()` only the events inside `[start, end)`, so an interval
  straddling the leading edge lost its opener and was counted by NOBODY: a
  chapter-close burst aged out whole intervals at once and the sliding total
  fell by more than the elapsed time — read on the dashboard as "hours being
  deducted when chapters close". The edge rule lives HERE and not in the
  feeding because `sessions()` is the one definition of what an interval is,
  and the timesheet blocks and the total beside them must stay one pass: a
  caller that filtered its own events would be a second definition, and the
  blocks would disagree with the total the moment the two drifted. The caller
  keeps one duty only — fetch from `start - GAP`, since nothing older than the
  longest countable interval can pair into the window anyway.

The signal is the timestamp of the events themselves. In v1 it was `activity`
events that were local-only and never reached the server, so hours were
systematically low and irreproducible after a rebuild.
"""

from __future__ import annotations

from typing import Sequence, TypedDict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

GAP = 30 * 60.0


class Session(TypedDict):
    """A run of counted intervals on ONE card, with nothing dropped inside it.

    `start`/`end` are wall-clock, which is what makes a timesheet drawable: two
    actors' blocks can be laid on one axis and read against each other.
    """

    start: float
    end: float
    task: str
    seconds: float


def sessions(stamps: Sequence[tuple[float, str]], since: float | None = None) -> list[Session]:
    """One actor's timestamped events → the blocks of time that were COUNTED.

    THE one definition of what an interval is. `spent()` is a fold of this and
    computes nothing of its own: two functions each deciding what counts is how
    a total and the timeline under it drift into disagreeing on screen, and the
    drift is invisible until somebody adds the blocks up by hand.

    Each interval runs between two consecutive events and is credited to the
    card of the event that CLOSES it — once. An interval longer than GAP is
    dropped whole (never capped), and the time it held is not in any session:
    that is the wall-clock a reader can see between two blocks.

    Consecutive counted intervals merge into ONE session while they are on the
    same card and touch end-to-start. A dropped gap breaks the run because the
    blocks stop touching; a change of card breaks it because the question a
    timesheet answers is "what was it working on at 15:40".

    `since` is the window's leading edge: an interval is kept when the stamp
    that CLOSES it is at or after it, whatever its opener. Feed the events from
    `since - GAP` and the window's sum stops depending on where the edge cuts —
    the header of this module says what the alternative cost.
    """
    out: list[Session] = []
    ordered = sorted(stamps)
    for (before, _), (after, task) in zip(ordered, ordered[1:], strict=False):
        delta = after - before
        if not 0 < delta <= GAP or (since is not None and after < since):
            continue
        last = out[-1] if out else None
        if last is not None and last["task"] == task and last["end"] == before:
            last["end"] = after
            last["seconds"] += delta
        else:
            out.append({"start": before, "end": after, "task": task, "seconds": delta})
    return out


def spent(stamps: Sequence[tuple[float, str]], since: float | None = None) -> dict[str, float]:
    """Seconds per card, from one actor's timestamped events.

    A fold of `sessions()` — see there for what an interval is, what `since`
    means, and why this function no longer decides either.
    """
    totals: dict[str, float] = {}
    for block in sessions(stamps, since):
        totals[block["task"]] = totals.get(block["task"], 0.0) + block["seconds"]
    return totals


def total(stamps: Sequence[tuple[float, str]], since: float | None = None) -> float:
    return sum(spent(stamps, since).values())


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
