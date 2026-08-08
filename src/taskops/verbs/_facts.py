"""Gathering the facts a guard needs, and finding a card without guessing.

The guards in `core/machine.py` are pure; somebody has to read the world for
them. That is here, in exactly one place, so "who holds this card" cannot be
answered two different ways in two verbs (v1 answered it in four).
"""

from __future__ import annotations

from ..core import review, machine, mentions
from ..store import reviews
from .._errors import NotFound
from ..core.types import CLOSED, Card, Event, Milestone
from ..store.stores import Stores


def find(stores: Stores, task: str) -> Card:
    card = stores.state()["cards"].get(task)
    if card is None:
        raise NotFound(f"{task} is not a card on this board — taskops_card query=… to search")
    return card


def milestone_of(stores: Stores, card: Card) -> Milestone | None:
    return stores.state()["milestones"].get(card["milestone"])


def open_milestone(stores: Stores) -> Milestone | None:
    """The single open milestone, or None if there are zero or several."""
    open_ones = [m for m in stores.state()["milestones"].values() if m["status"] == "open"]
    return open_ones[0] if len(open_ones) == 1 else None


def holders(stores: Stores, now: float) -> dict[str, str]:
    """task -> actor, for every LIVE lease. This is what makes a card `doing`."""
    return {lease["task"]: lease["actor"] for lease in stores.live.held(now)}


def pending_mentions(stores: Stores, actor: str) -> list[mentions.Mention]:
    """What `actor` was addressed about and has not answered — the world half of
    `core/mentions.pending()`, in the one place that reads it.

    Board-wide on purpose, never per milestone: a mention addresses a PERSON,
    and missing one because you were reading another chapter is exactly the
    miss this exists to prevent.
    """
    cards = stores.state()["cards"]
    closed = {ident for ident, card in cards.items() if card["status"] in CLOSED}
    return mentions.pending(stores.threads(), actor, closed)


def reviewing(stores: Stores, now: float) -> dict[str, str]:
    """task -> actor, for every LIVE review lease — what makes a card `reviewing`."""
    return reviews.reviewing(stores.live, now)


def review_leases(stores: Stores, now: float) -> dict[str, reviews.Held]:
    """task -> the whole live review lease, actor AND when the review began.

    `reviewing()` above is this one's actor half, and it is what `core/graph.py`
    takes, because deriving the state only asks WHETHER somebody holds it. A
    caller that also has to say how much of the review lease is left reads this
    instead — same single query, no second trip to the store."""
    return reviews.held(stores.live, now)


def standings(stores: Stores) -> dict[str, review.Standing]:
    """Every card's standing with its reviewer — the world half of
    `core/review.pending()`, folded from the same threads as mentions."""
    return review.pending(stores.threads())


def facts(stores: Stores, card: Card, now: float) -> machine.Facts:
    return machine.Facts(
        status=card["status"],
        assignee=card["assignee"],
        holder=stores.live.holder(card["id"], now),
        commits=sum(1 for e in stores.events(card["id"]) if e["kind"] == "commit"),
        standing=review.standing(stores.events(card["id"])),
    )


def commits_of(events: list[Event]) -> list[Event]:
    return [e for e in events if e["kind"] == "commit"]


def merged_into(events: list[Event]) -> str:
    """The milestone branch this card was integrated into, or '' if it was not."""
    for event in reversed(events):
        if event["kind"] == "merged":
            return str(event["body"].get("into", ""))
    return ""


def last_release(events: list[Event]) -> str:
    """The note the previous worker left. It is shown verbatim on the next take —
    in v1 this was recorded and never displayed, so every worker started cold."""
    for event in reversed(events):
        if event["kind"] == "released":
            return str(event["body"].get("note", ""))
    return ""


def branch_of(card: Card) -> str:
    """The card's branch is its id. No slug, so a retitled card cannot grow a
    second branch (v1's ghost branches and the whole `_whichbranch` saga)."""
    return card["id"]


def worktree_of(card: Card) -> str:
    return f".taskops/trees/{card['id']}"
