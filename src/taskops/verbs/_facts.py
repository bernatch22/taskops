"""Gathering the facts a guard needs, and finding a card without guessing.

The guards in `core/machine.py` are pure; somebody has to read the world for
them. That is here, in exactly one place, so "who holds this card" cannot be
answered two different ways in two verbs (v1 answered it in four).
"""

from __future__ import annotations

from ..core import (
    review,
    machine,
    reports as reporting,  # `reports()` below is this module's door to it
    mentions,
)
from ..store import reviews
from .._errors import NotFound
from ..core.types import CLOSED, PROJECT, EVERYTHING, Card, Event, Milestone
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


LANDED_SHOWN = 20
"""How many LANDED chapters `chapters()` carries, newest first.

Same argument as `pulse.DONE_SHOWN`, one level up. Open chapters are bounded by
how much work is in flight; landed ones only ever grow, so they are capped
rather than sent whole — the log is replayed forever and this list rides on
every dashboard poll. 20 is generous where `DONE_SHOWN` is tight because
chapters accrue at a wholly different rate: cards are a dozen a day, a chapter
is a human sitting down to write a plan, so 20 is months of history rather than
a day of it. The caller is handed the real total alongside, the way
`done_total` sits behind `groups.done`."""


def chapters(stores: Stores) -> tuple[list[Milestone], int]:
    """Every OPEN chapter, then the `LANDED_SHOWN` most recent landed ones, and
    how many landed there really are.

    Landed chapters are in the SAME list and not a second key on purpose: a
    chapter carries its own `status`, so every consumer that needs the
    distinction already has it, and a reader asking "which chapters exist"
    should not have to know there are two lists. What it costs is that the
    length of this list stopped meaning "open chapters" — the two places that
    read it that way (`mcp/render.py::_header` and the dashboard's picker)
    filter by status, and a test pins each.

    Open first, landed after, because that is the order to read them: a
    consumer drawing the list top to bottom gets what is in flight before what
    is history without sorting anything. `dropped` is neither — an abandoned
    chapter is not work anybody reviews — and falls out here."""
    everything = list(stores.state()["milestones"].values())
    landed = sorted(
        (m for m in everything if m["status"] == "landed"),
        key=lambda m: m["created"],
        reverse=True,
    )
    open_now = [m for m in everything if m["status"] == "open"]
    return open_now + landed[:LANDED_SHOWN], len(landed)


REPORTS_SHOWN = 20
"""How many registered reports ride on a read, newest first.

`LANDED_SHOWN`'s argument one notch along: reports only ever accumulate, so the
list is capped and the honest total travels beside it (`done_total`'s idiom,
which this chapter's rules make a requirement rather than a habit). 20 because a
chapter is narrated a handful of times, so this is the whole story for a focused
chapter and a generous tail for the board."""


def reports(stores: Stores, milestone: str = "") -> tuple[list[reporting.Report], int]:
    """A chapter's reports, newest first, and how many there really are.

    The world half of `core/reports.py::of` — one read of the PROJECT thread,
    which is where a `report` event lives (it is about a chapter, not a card).
    Nothing is stored: the list is folded per read, so a report cannot exist in
    the log and be missing from the list, which is the failure a `reports` table
    would eventually produce.
    """
    rows = reporting.of(stores.events(PROJECT), milestone)
    return rows[:REPORTS_SHOWN], len(rows)


def in_scope(stores: Stores, given: str) -> Milestone | None:
    """The chapter a read is narrowed to: the one NAMED, NONE for `EVERYTHING`
    (`core/types.py`), else the single open one (None for zero or several).

    A named chapter is looked up by id and NOT filtered by status. That is the
    whole point of a landed chapter still being listed — focusing one is how
    anybody reviews finished work — and a status filter here would have made
    the picker offer something the server then refused to resolve."""
    if given:
        return None if given == EVERYTHING else stores.state()["milestones"].get(given)
    return open_milestone(stores)


def holders(stores: Stores, now: float) -> dict[str, str]:
    """task -> actor, for every LIVE lease. This is what makes a card `doing`."""
    return {lease["task"]: lease["actor"] for lease in stores.live.held(now)}


def pending_mentions(stores: Stores, actor: str) -> list[mentions.Mention]:
    """What `actor` was addressed about and has not answered — the world half of
    `core/mentions.pending()`, in the one place that reads it.

    Board-wide on purpose, never per milestone: a mention addresses a PERSON,
    and missing one because you were reading another chapter is exactly the
    miss this exists to prevent.

    CLOSED cards are excluded and that cuts BOTH ways (2026-08-14): closing
    clears the mentions written before it — the point — and a mention written
    AFTER the close is undeliverable, in silence. The comment itself is still
    accepted, so the postscript reaches the thread; only the address is dropped.
    Kept: a closed card owes nobody a reply, and this set is what bounds the
    scan to work in flight — the log is replayed forever. Pinned by
    `test_a_mention_written_on_an_already_closed_card_is_undeliverable`.
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
