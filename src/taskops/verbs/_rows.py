"""The rows of `board` — how one card, one teammate and the hours fold become
payload lines. Split out of `pulse.py` so the verb keeps room to grow: pulse
owns the GROUPS and their order, this file owns the shape of a single row.
"""

from __future__ import annotations

from typing import Any

from . import _args, report
from ..core.types import Card
from ..store.stores import Stores


def row(stores: Stores, card: Card, now: float, live: dict[str, str]) -> dict[str, Any]:
    """One line of the board. `quiet_for` is what makes STALLED actionable: it
    says how long since the owner last said anything, not a guess about why."""
    holder = live.get(card["id"])
    lease = stores.live.lease(card["id"], now) if holder else None
    return {
        "id": card["id"],
        "title": card["title"],
        # The chapter's ID, never its title: `milestones` already carries the
        # words, so a reader joins the two and neither can age past the other.
        "milestone": card["milestone"],
        "priority": card["priority"],
        "assignee": card["assignee"],
        "holder": holder,
        "since": lease["acquired"] if lease else card["updated"],
        "quiet_for": None if holder else now - card["updated"],
        "files": card["files"],
        "labels": card["labels"],
    }


def team(stores: Stores, now: float) -> list[dict[str, Any]]:
    return [
        {"actor": actor, "seen": seen, "ago": now - seen}
        for actor, seen in stores.live.present(now - 24 * 3600)
    ]


def hours(stores: Stores, args: _args.Args, now: float, window: str) -> dict[str, Any]:
    """`window="7d"` folds the report into the same read — one call, one picture."""
    tz = _args.text(args, "tz", default="UTC") or "UTC"
    return report.summary(stores, now, report.days(window), tz)
