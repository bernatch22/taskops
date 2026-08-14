"""Dependencies, derived states, and the cycles that are refused at the write.

`ready` and `blocked` are computed here and stored nowhere. A card is ready
when it is open, has no open dependency and nobody owns it. Closing a blocker
frees its dependents with no event and no writer — which is exactly why the
whole promotion machinery of v1 does not exist.

A cycle is refused when the edge is written, not discovered later by a
traversal that hangs. v1 accepted a 2-cycle silently and the two cards were
invisible in every list that filtered by "ready".
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Mapping
from collections import deque

from .types import CLOSED, Card
from .._errors import Refused, NotFound

if TYPE_CHECKING:
    from .review import Standing

Holders = Mapping[str, str]
"""task id -> the actor holding a LIVE lease on it. The live store's answer,
passed in rather than looked up, because this module stays pure."""


def blockers(cards: dict[str, Card], ident: str) -> list[str]:
    """Dependencies of `ident` that have not closed."""
    card = cards.get(ident)
    if card is None:
        return []
    return [d for d in card["after"] if (o := cards.get(d)) and o["status"] not in CLOSED]


def blocks(cards: dict[str, Card], ident: str) -> list[str]:
    """Cards waiting on `ident` — the reverse edge, computed on demand."""
    return sorted(c["id"] for c in cards.values() if ident in c["after"])


def subtasks(cards: dict[str, Card], ident: str) -> list[str]:
    return sorted(c["id"] for c in cards.values() if c["parent"] == ident)


def derived(
    cards: dict[str, Card],
    card: Card,
    holders: Holders | None = None,
    reviewing: Holders | None = None,
    standings: Mapping[str, "Standing"] | None = None,
) -> str:
    """What to SHOW: the stored status, refined by who is actually on it.

        done | dropped   as stored — the card is closed
        reviewing        somebody holds a live REVIEW lease on it, right now
        review           handed in and nobody has judged it → assign a reviewer
        doing            SOMEBODY HOLDS THE WORK LEASE, right now
        changes          the last verdict asked for changes → back to the worker
        blocked          a dependency has not closed
        stalled          it has an owner but nobody is running it
        ready            takeable

    `doing` is computed from the live lease and nowhere else. That is the whole
    fix: a worker that dies stops renewing, and its card leaves `doing` by
    itself — no sweep, no writer, nothing to remember to run. The review states
    work identically: the two new parameters default to None ("nothing under
    review"), so a board that never sets `review` derives exactly as before.

    BOTH review states are gated on `card["review"]`, not only the first one:
    `review` is EDITABLE, so it can be turned OFF after a verdict was written,
    and a card whose flag is off must derive exactly as it did before the
    feature existed — otherwise the flag is not one you can turn off.

    The STORED status is answered FIRST, above every live fact — so a closed
    card reads `done` or `dropped` and can never derive `stalled`, however long
    its lease has been gone. `stalled` lives on the open branch alone.

    Two placements that are deliberate: `review` sits ABOVE `doing` (a
    submitted card whose worker still holds its lease is waiting for a
    reviewer, and that is the move to show), and `changes` sits BELOW `doing`
    (a worker back on the card after a verdict is working, not waiting — the
    card only reads `changes` when nobody is on it).
    """
    if card["status"] in CLOSED:
        return card["status"]
    stood = (standings or {}).get(card["id"])
    if card["id"] in (reviewing or {}):
        return "reviewing"
    if card.get("review") and stood and not stood.verdict:
        return "review"
    if card["id"] in (holders or {}):
        return "doing"
    if card.get("review") and stood and stood.verdict == "changes":
        return "changes"
    if blockers(cards, card["id"]):
        return "blocked"
    return "stalled" if card["assignee"] else "ready"


def ready(cards: dict[str, Card], holders: Holders | None = None) -> list[Card]:
    """Takeable right now, urgent first, then oldest — a stable order."""
    pool = [c for c in cards.values() if derived(cards, c, holders) == "ready"]
    return sorted(pool, key=lambda c: (c["priority"], c["created"]))


def mine(cards: dict[str, Card], actor: str, holders: Holders | None = None) -> list[Card]:
    """What THIS worker may pick up: its own cards, stalled or already held by it."""
    pool = [
        c
        for c in cards.values()
        if c["assignee"] == actor
        and c["status"] not in CLOSED
        and (holders or {}).get(c["id"], actor) == actor
    ]
    return sorted(pool, key=lambda c: (c["priority"], c["created"]))


def reaches(cards: dict[str, Card], start: str, target: str) -> bool:
    """Is `target` reachable from `start` following `after` edges?"""
    seen: set[str] = set()
    queue = deque([start])
    while queue:
        node = queue.popleft()
        if node == target:
            return True
        if node in seen:
            continue
        seen.add(node)
        card = cards.get(node)
        if card is not None:
            queue.extend(card["after"])
    return False


def check_dep(cards: dict[str, Card], task: str, after: str) -> None:
    """Refuse a dependency edge that cannot exist. Called by every writer of `after`."""
    if task == after:
        raise Refused(f"{task} cannot depend on itself")
    if after not in cards:
        raise NotFound(f"{after} does not exist — dependencies name a card id")
    if reaches(cards, after, task):
        raise Refused(
            f"{task} after {after} closes a cycle ({after} already waits on {task}). "
            "Drop one edge: the graph is what makes 'ready' meaningful."
        )
