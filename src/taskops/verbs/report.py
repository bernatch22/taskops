"""report — hours and what moved, over calendar days.

The signal is the timestamps of the events themselves, and since every call
reaches the board, the signal is where the arithmetic is. v1 measured with
`activity` events that were local-only and never left the machine, so hours
came out systematically low and changed after every rebuild.

The arithmetic itself lives in `core/hours.py`: a gap longer than 30 minutes
is dropped, never capped, and an interval belongs to the window its CLOSING
stamp is in. This module's whole part in that second rule is the FETCH — every
window is read from `start - hours.GAP`, so an opener just before the edge is
still in hand to pair with, and nothing older than the longest countable
interval can reach in. The keeping is `sessions(since=start)`'s decision, once.
The counts beside the hours (`closed`, `commits`, `cards`) stay strictly
inside the window: they count EVENTS, not intervals, so the pre-roll is not
theirs to see.
"""

from __future__ import annotations

from typing import Any

from . import _args
from .. import _clock
from ..core import hours
from ..core.types import Event
from ..store.stores import Stores

#: How many blocks of one actor's timesheet travel in one fold. A day rarely
#: reaches it; a 90-day window on a busy actor would, and the payload is a
#: single answer, not a stream. `sessions_total` always says the real number.
SESSIONS = 240


def run(stores: Stores, actor: str, args: _args.Args) -> dict[str, Any]:
    now = _clock.now()
    stores.live.renew(actor, now)
    return summary(stores, now, days(_args.text(args, "window", default="7d")), _zone(args))


def summary(stores: Stores, now: float, span: int, tz: str) -> dict[str, Any]:
    spans = hours.windows(now, tz, span)
    start, end = spans[0][1], spans[-1][2]
    events = _fetch(stores, start, end)
    return {
        "from": start,
        "to": end,
        "days": [_day(stores, label, lo, hi) for label, lo, hi in spans],
        "by_actor": _by_actor(events, start),
        "total": {
            "seconds": sum(hours.total(p, start) for p in _stamps(events).values()),
            "closed": sum(1 for e in events if e["ts"] >= start and _closed(e)),
        },
    }


def days(window: str) -> int:
    """`7d`, `7`, `1d` → an integer number of calendar days, 1..90."""
    text = window.strip().lower().removesuffix("d") or "7"
    return max(1, min(90, int(text))) if text.isdigit() else 7


def _zone(args: _args.Args) -> str:
    return _args.text(args, "tz", default="UTC") or "UTC"


def _fetch(stores: Stores, start: float, end: float) -> list[Event]:
    """The window's events, plus GAP of pre-roll so an interval straddling the
    leading edge still has its opener. Never widen `start` itself: the pre-roll
    exists to be PAIRED with, and `sessions(since=start)` is what decides which
    of those pairs the window keeps."""
    return stores.cache.window(start - hours.GAP, end)


def _day(stores: Stores, label: str, start: float, end: float) -> dict[str, Any]:
    events = _fetch(stores, start, end)
    inside = [e for e in events if e["ts"] >= start]
    return {
        "day": label,
        "by_actor": _by_actor(events, start),
        "closed": sorted({e["task"] for e in inside if _closed(e)}),
        "commits": sum(1 for e in inside if e["kind"] == "commit"),
    }


def _by_actor(events: list[Event], since: float) -> dict[str, dict[str, Any]]:
    """Everything an actor did INSIDE THE WINDOW — hours, cards touched, cards
    closed, commits, and the SESSIONS the hours are made of. All of it is the
    same pass over the same events: `closed` and `commits` are counts of events
    already in hand, never a stored figure and never a lifetime one. The screen
    says "today" or "7 days" beside them because that is exactly what they
    measure. `events` arrives with GAP of pre-roll in front of `since`: it is
    there so `sessions()` can pair an interval across the edge, and only the
    hours may see it — every count below is folded over `within`.

    `sessions` is not a second computation — `core/hours.py::sessions` is what
    `spent()` itself folds, so the blocks a timesheet draws and the total beside
    them cannot disagree. It travels capped, with `sessions_total` next to it
    (`done_total`'s pattern): a fortnight of a busy actor is unbounded, and a
    truncated list that does not say so is a screen that quietly loses time.
    """
    within = [e for e in events if e["ts"] >= since]
    inside, padded = _stamps(within), _stamps(events)
    closed, commits = _counts(within)
    out: dict[str, dict[str, Any]] = {}
    for actor, points in inside.items():
        blocks = hours.sessions(padded[actor], since)
        seconds = sum(b["seconds"] for b in blocks)
        out[actor] = {
            "seconds": seconds,
            "human": hours.human(seconds),
            "cards": sorted({task for _, task in points}),
            "closed": closed.get(actor, 0),
            "commits": commits.get(actor, 0),
            "sessions": blocks[:SESSIONS],
            "sessions_total": len(blocks),
        }
    return out


def _counts(events: list[Event]) -> tuple[dict[str, int], dict[str, int]]:
    closed: dict[str, int] = {}
    commits: dict[str, int] = {}
    for event in events:
        if _closed(event):
            closed[event["actor"]] = closed.get(event["actor"], 0) + 1
        elif event["kind"] == "commit":
            commits[event["actor"]] = commits.get(event["actor"], 0) + 1
    return closed, commits


def _stamps(events: list[Event]) -> dict[str, list[tuple[float, str]]]:
    stamps: dict[str, list[tuple[float, str]]] = {}
    for event in events:
        stamps.setdefault(event["actor"], []).append((event["ts"], event["task"]))
    return stamps


def _closed(event: Event) -> bool:
    return event["kind"] == "status" and event["body"].get("to") == "done"
