"""The dossier: everything a worker needs about a card, in one payload.

This is the contract of ARCHITECTURE.md §6 and the replacement for every
prompt v1 injected through hooks. Three rules:

* **Never truncated.** The whole spec, the whole thread. A summary is where
  context goes to die.
* **The previous `released` note is part of it.** Resuming is the normal case,
  not the exception.
* **It travels in the response of the call the agent already makes** (`take`,
  `card`), so nothing can be out of sync with the board it describes.
"""

from __future__ import annotations

from typing import Any

from . import _facts
from ..core import graph, hours, review
from ..core.types import Card, Event
from ..store.stores import Stores


def dossier(stores: Stores, actor: str, card: Card, now: float) -> dict[str, Any]:
    state = stores.state()
    cards = state["cards"]
    events = stores.events(card["id"])
    lease = stores.live.lease(card["id"], now)
    stood = review.standing(events)
    return {
        "card": card,
        "state": graph.derived(
            cards,
            card,
            _facts.holders(stores, now),
            _facts.reviewing(stores, now),
            {card["id"]: stood} if stood.submitted_at else None,
        ),
        # Where it stands with its reviewer — the "changes" note travels verbatim.
        "standing": stood._asdict() if stood.submitted_at else None,
        "milestone": state["milestones"].get(card["milestone"]),
        "history": events,  # complete, in order, never cut
        "resume": _facts.last_release(events),
        "commits": [e["body"] for e in _facts.commits_of(events)],
        "merged_into": _facts.merged_into(events),
        # The card this one is PART OF, resolved — not just an id. An id is not
        # something a worker can read: in v1 a child never learned what it
        # belonged to while its parent had listed it all along, and a subtask
        # read without its epic gets solved correctly for the wrong problem.
        "epic": _epic(cards, card),
        "seconds": attended(events),
        "blockers": [_brief(cards, i) for i in card["after"]],
        "blocks": [_brief(cards, i) for i in graph.blocks(cards, card["id"])],
        "subtasks": [_brief(cards, i) for i in graph.subtasks(cards, card["id"])],
        "collisions": collisions(stores, card, now),
        "elsewhere": elsewhere(stores, card, now),
        "lease": lease,
        "branch": _facts.branch_of(card),
        "worktree": _facts.worktree_of(card),
        "pulse": pulse(stores, actor, now, card["milestone"]),
    }


def collisions(stores: Stores, card: Card, now: float) -> list[dict[str, Any]]:
    """Cards claiming the same files right now. A warning, never a lock — the
    worktrees already make it impossible to overwrite each other's edits."""
    mine = set(card["files"])
    if not mine:
        return []
    out: list[dict[str, Any]] = []
    for other in stores.state()["cards"].values():
        if other["id"] == card["id"] or other["status"] != "open":
            continue
        shared = sorted(mine & set(other["files"]))
        if not shared:
            continue
        holder = stores.live.holder(other["id"], now)
        # Somebody is on it, or somebody was handed it: both are people you can
        # collide with. An open card nobody owns is not a collision, it is a
        # plan — listing those would bury the warning in noise.
        if holder or other["assignee"]:
            out.append(
                {
                    "id": other["id"],
                    "title": other["title"],
                    "files": shared,
                    "holder": holder or other["assignee"],
                    "started": bool(holder),
                }
            )
    return out


def elsewhere(stores: Stores, card: Card, now: float) -> list[dict[str, Any]]:
    """Who else is working RIGHT NOW, on what — the panorama v1's session-start
    hook gave once and then never again.

    Only live holders, never the whole board: this rides inside a take, and a
    list of every open card would bury the spec it sits above. `collisions` is
    the sharper warning (the same FILES); this is the room, so an agent knows
    who to reach before it needs to.
    """
    cards = stores.state()["cards"]
    return sorted(
        (
            {
                "id": other["id"],
                "title": other["title"],
                "holder": holder,
                "milestone": other["milestone"],
            }
            for task, holder in _facts.holders(stores, now).items()
            if task != card["id"] and (other := cards.get(task)) is not None
        ),
        key=lambda row: str(row["holder"]),
    )


def pulse(stores: Stores, actor: str, now: float, milestone: str = "") -> dict[str, Any]:
    """The one-line heartbeat appended to every tool result (§2.3, layer 3).

    `actor` is required rather than optional because the mention count is the
    half of this line that is addressed to ONE reader: defaulted, a caller that
    forgot it would report a silent zero, and "nobody misses a mention" would
    hold everywhere except the call that forgot.
    """
    state = stores.state()
    cards = [c for c in state["cards"].values() if not milestone or c["milestone"] == milestone]
    index = state["cards"]
    live = _facts.holders(stores, now)
    counts = {"doing": 0, "ready": 0, "blocked": 0, "stalled": 0, "done": 0}
    for card in cards:
        shown = graph.derived(index, card, live)
        if shown in counts:
            counts[shown] += 1
    stone = state["milestones"].get(milestone)
    return {
        "milestone": stone["title"] if stone else "",
        "goal": stone["goal"] if stone else "",
        "counts": counts,
        # Rides on every result, so a mention is found within one call even when
        # nobody opened the board this turn. This is the whole "every turn"
        # guarantee, and it needs no hook because nothing was ever NOT called.
        "mentions": len(_facts.pending_mentions(stores, actor)),
    }


def attended(events: list[Event]) -> float:
    """How long this card was WORKED, from its own events, per actor.

    A floor, never an estimate: it is the sum of the gaps between one actor's
    consecutive events on this card, dropping any gap over 30 minutes whole
    (`core/hours`). It is the same arithmetic the report uses, so a card and a
    board can never quote two different numbers for the same work.
    """
    per_actor: dict[str, list[tuple[float, str]]] = {}
    for event in events:
        per_actor.setdefault(event["actor"], []).append((event["ts"], event["task"]))
    return sum(hours.total(stamps) for stamps in per_actor.values())


def _epic(cards: dict[str, Card], card: Card) -> dict[str, Any] | None:
    """The parent, resolved: id, title AND its spec — the sentence that makes
    this card's spec make sense."""
    parent = cards.get(card["parent"] or "")
    if parent is None:
        return None
    return {
        "id": parent["id"],
        "title": parent["title"],
        "spec": parent["spec"],
        "status": graph.derived(cards, parent),
    }


def _brief(cards: dict[str, Card], ident: str) -> dict[str, Any]:
    card = cards.get(ident)
    if card is None:
        return {"id": ident, "title": "(unknown)", "status": "?"}
    return {
        "id": card["id"],
        "title": card["title"],
        "status": graph.derived(cards, card),
        "assignee": card["assignee"],
    }
