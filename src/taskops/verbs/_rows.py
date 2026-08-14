"""The rows of `board` — how one card, one teammate and the hours fold become
payload lines. Split out of `pulse.py` so the verb keeps room to grow: pulse
owns the GROUPS and their order, this file owns the shape of a single row.
"""

from __future__ import annotations

from typing import Any

from . import _args, _facts, report
from ..core.types import Card, Event
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


def forensics(events: list[Event], now: float) -> dict[str, Any]:
    """The extra keys a STALLED row carries, derived from the card's thread.

    `quiet_for` says HOW LONG the owner has been silent; these two say what the
    silence is made of, which is the difference between resuming a worker and
    reassigning the card. Five workers died at once and every stalled row read
    only "quiet for 1h": took-then-nothing (never started), comment-then-nothing
    (thinking out loud, then gone) and commit-then-nothing (work on the branch,
    worth resuming) are three different moves behind one number.

    - `last_event = {kind, ago}` — the LAST thing on the thread and its age in
      seconds. `None` on a thread with no events, which a card cannot have in
      practice (it is created by one) but the shape must survive anyway.
    - `commits` — how many commit events are bound to the card. Not "has
      commits": one commit and eleven are different amounts of work to throw
      away, and the count costs nothing over the same list.

    NOTHING here is stored and nothing records a cause of death: the lease's
    only heartbeat is MCP traffic, so the board cannot know WHY a holder stopped,
    only WHAT it last said (ARCHITECTURE §12). Both keys ride ONLY on the stalled
    group, the way `waiting_on` rides only on blocked — every other row stays
    byte-compatible, and no row pays for a read it does not use.
    """
    last = events[-1] if events else None
    return {
        "last_event": {"kind": last["kind"], "ago": now - last["ts"]} if last else None,
        "commits": len(_facts.commits_of(events)),
    }


def team(stores: Stores, now: float) -> list[dict[str, Any]]:
    return [
        {"actor": actor, "seen": seen, "ago": now - seen}
        for actor, seen in stores.live.present(now - 24 * 3600)
    ]


def hours(stores: Stores, args: _args.Args, now: float, window: str) -> dict[str, Any]:
    """`window="7d"` folds the report into the same read — one call, one picture.
    The spelling is `report.parse`'s business, not this one's: `7d`, `month`,
    `YYYY-MM` and `total` all arrive here as the same string."""
    tz = _args.text(args, "tz", default="UTC") or "UTC"
    return report.summary(stores, now, window, tz)
