"""When a peer-reviewed card enters review, the SERVER picks its reviewer. One reviewer.

The design this replaces was broadcast: every review appeared in every session's sweep and
crossed the channel as a notification to everybody, which produced all three failures of one
live night — two free developers starting the same review, the author drowning in echoes of
its own handovers, and a feed nobody could distinguish signal in. A review is not news. It is
an ASSIGNMENT, and an assignment belongs to exactly one person.

**The server decides because only the server sees everyone.** Presence rides every heartbeat,
so at the moment a card enters review the store knows which developers are actually here.
The choice is deterministic, so two clones asking "who should review X" can never disagree:

    1. connected developers only, the author's dev excluded
    2. fewest reviews already routed to them        — the equity the team asked for
    3. freshest heartbeat                           — prefer whoever is active right now
    4. alphabetical                                 — no coin flips, ever

Nobody connected but the author? The card stays unrouted and open to whoever shows up, which
is exactly what a solo developer at 3am needs.

Routing EXPIRES. The chosen dev owns the review for `ROUTE_TTL`; after that the card opens to
every eligible dev — the sweep starts showing it, and the lease still guarantees a single
checker in the reopened window. The timeout is on the routing only, never the work.
"""

from __future__ import annotations

from .._clock import now
from ..contracts import Task
from ..storage import Store
from .identity import parse
from .log import record

# ruff: noqa: I001

__all__ = ["route_review", "ROUTE_TTL", "PRESENCE_WINDOW", "routed_to", "route_is_fresh",
           "routed_elsewhere", "release_routing"]

PRESENCE_WINDOW = 600.0
"""Seconds of silence before a dev stops counting as connected. Ten minutes: longer than any
--wait poll interval, shorter than a lunch break."""

ROUTE_TTL = 1800.0
"""How long the chosen reviewer owns the review before it opens to everybody eligible."""


def route_review(store: Store, task: Task, author: str) -> str:
    """Pick the reviewer, assign the card to them, tell them — or "" when nobody is there."""
    chosen = _pick(store, author)
    if not chosen:
        return ""
    store.tasks.set_assignee(task["id"], chosen, when=now())
    record(store, task=task["id"], actor=author, kind="message",
           body={"text": f"{task['id']} espera tu revisión: “{task['title']}”. "
                         f"Claim it first (taskops_next task={task['id']}) — that is what "
                         f"keeps a second reviewer out.",
                 "mentions": [chosen], "routed_review": True})
    return chosen


def _pick(store: Store, author: str) -> str:
    """The reviewer, preferring developers with a session open and never insisting on one.

    Both halves were paid for. Routing to anybody merely *present* sent a review to a manager
    who had created the cards from a terminal and gone; requiring a session sent three reviews
    to NOBODY, because the session id was not reaching the store that routes — and a card
    routed to nobody is an orphan in review that no message ever mentions.

    So the session narrows the field when the signal is there, and is ignored when it is not.
    A ghost reviewer is a card that waits and then expires; no reviewer at all is a card that
    nothing will ever say out loud, which is strictly the worse failure.
    """
    mine = _dev(author)
    when = now() - PRESENCE_WINDOW
    here = store.presence.devs(since=when, in_session=True)
    if not here:
        # NOBODY carries a session — so the signal itself is not arriving on this board, and
        # falling back to whoever is merely present beats routing to no one. The moment ANY
        # dev has a session the signal works, and "no other in-session dev" is a fact rather
        # than a gap: do not fall back then. That distinction is the whole rule. Without it a
        # team that never overlaps — one works at night, the other in the morning — routed
        # every single review to the manager who had planned the cards from a terminal and
        # gone, which is exactly the asynchronous case this has to serve.
        here = store.presence.devs(since=when)
    candidates = [dev for dev in here if dev and dev != mine]
    if not candidates:
        return ""
    load = _review_load(store)
    candidates.sort(key=lambda dev: (load.get(dev, 0), -here[dev], dev))
    return f"dev:{candidates[0]}"


def _review_load(store: Store) -> dict[str, int]:
    """Reviews already routed to each dev — the number equity balances on."""
    out: dict[str, int] = {}
    for card in store.tasks.with_status(("review",)):
        dev = _dev(card["assignee"])
        if dev:
            out[dev] = out.get(dev, 0) + 1
    return out


def release_routing(store: Store, task: Task) -> None:
    """Drop the routing when the card stops being a review.

    Routing borrows `assignee` to name the reviewer, and an assignment is what HIDES a card
    from everybody else. So a routed review that got rejected stayed assigned to the reviewer
    who rejected it: the worker whose findings those are could not claim its own card back,
    and the card sat `ready`, invisible, waiting on somebody with nothing left to do.

    Only a `dev:` assignee is dropped. An `agent:` one is a dispatch — that card was chosen for
    that worker and clearing it would throw the dispatch away.
    """
    if task["status"] != "review" and task["assignee"].startswith("dev:"):
        store.tasks.set_assignee(task["id"], "", when=now())


def routed_to(task: Task) -> str:
    """The dev a review is currently routed to, or "".

    A `dev:` assignee and ONLY a `dev:` assignee is a routing. An `agent:` one means something
    else entirely — the worker that carried the card here — and reading it as a routing would
    hide every unrouted review behind its own author, which is the opposite of the point.
    """
    owner = task["assignee"]
    return _dev(owner) if task["status"] == "review" and owner.startswith("dev:") else ""


def route_is_fresh(task: Task, *, at: float | None = None) -> bool:
    """Does the routed reviewer still own this exclusively? Stale routing opens the card."""
    return ((now() if at is None else at) - task["updated"]) < ROUTE_TTL


def routed_elsewhere(task: Task, actor: str) -> bool:
    """Is this review exclusively somebody ELSE's right now?

    The one question the sweep asks about routing, answered here so `attention` never has to
    parse an actor id — it decides moves, this decides ownership.
    """
    owner = routed_to(task)
    return bool(owner) and route_is_fresh(task) and owner != _dev(actor)


def _dev(actor: str) -> str:
    try:
        return parse(actor)["dev"] if actor else ""
    except Exception:  # noqa: BLE001 — a legacy id routes to nobody rather than crashing
        return ""
