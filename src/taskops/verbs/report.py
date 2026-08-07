"""report — hours and what moved, over calendar days.

The signal is the timestamps of the events themselves, and since every call
reaches the board, the signal is where the arithmetic is. v1 measured with
`activity` events that were local-only and never left the machine, so hours
came out systematically low and changed after every rebuild.

The arithmetic itself lives in `core/hours.py`: a gap longer than 30 minutes
is dropped, never capped.
"""

from __future__ import annotations

from typing import Any

from . import _args
from .. import _clock
from ..core import hours
from ..core.types import Event
from ..store.stores import Stores


def run(stores: Stores, actor: str, args: _args.Args) -> dict[str, Any]:
    now = _clock.now()
    stores.live.renew(actor, now)
    return summary(stores, now, days(_args.text(args, "window", default="7d")), _zone(args))


def summary(stores: Stores, now: float, span: int, tz: str) -> dict[str, Any]:
    spans = hours.windows(now, tz, span)
    start, end = spans[0][1], spans[-1][2]
    events = stores.cache.window(start, end)
    return {
        "from": start,
        "to": end,
        "days": [_day(stores, label, lo, hi) for label, lo, hi in spans],
        "by_actor": _by_actor(events),
        "total": {
            "seconds": sum(hours.total(p) for p in _stamps(events).values()),
            "closed": sum(1 for e in events if _closed(e)),
        },
    }


def days(window: str) -> int:
    """`7d`, `7`, `1d` → an integer number of calendar days, 1..90."""
    text = window.strip().lower().removesuffix("d") or "7"
    return max(1, min(90, int(text))) if text.isdigit() else 7


def _zone(args: _args.Args) -> str:
    return _args.text(args, "tz", default="UTC") or "UTC"


def _day(stores: Stores, label: str, start: float, end: float) -> dict[str, Any]:
    events = stores.cache.window(start, end)
    return {
        "day": label,
        "by_actor": _by_actor(events),
        "closed": sorted({e["task"] for e in events if _closed(e)}),
        "commits": sum(1 for e in events if e["kind"] == "commit"),
    }


def _by_actor(events: list[Event]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for actor, points in _stamps(events).items():
        seconds = hours.total(points)
        out[actor] = {
            "seconds": seconds,
            "human": hours.human(seconds),
            "cards": sorted({task for _, task in points}),
        }
    return out


def _stamps(events: list[Event]) -> dict[str, list[tuple[float, str]]]:
    stamps: dict[str, list[tuple[float, str]]] = {}
    for event in events:
        stamps.setdefault(event["actor"], []).append((event["ts"], event["task"]))
    return stamps


def _closed(event: Event) -> bool:
    return event["kind"] == "status" and event["body"].get("to") == "done"
