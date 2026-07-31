"""The team brief: who is connected right now, and what they are holding.

Assembled from two facts the store already keeps and nobody had ever joined. Presence rides
every heartbeat, so a dev that called anything in the last `PRESENCE_WINDOW` is here; a live
lease names the actor holding a card. Joined by DEV, because a developer and their agents are
one person — a session told that `ana`, `agent:ana/w1` and `agent:ana/verifier` are three busy
parties would read a two-person team as a crowd.

Why it is worth a session's opening screen: everything else a session starts with describes its
OWN state, so two sessions on one board each behave as though they were alone. That is not a
theory — it is how one card got implemented twice and how a review got started by two devs at
once. The cure is one paragraph of "here is who else is here", handed over before anybody types.
"""

from __future__ import annotations

from .._clock import now
from ..contracts.team import Mate, Team
from ..storage import Store
from .identity import parse
from .routereview import PRESENCE_WINDOW

__all__ = ["team"]


def team(store: Store, actor: str, *, at: float | None = None) -> Team:
    """Everyone connected but this actor's own dev, busiest first."""
    when = now() if at is None else at
    mine = _dev(actor)
    held = _held_by_dev(store, when)
    mates = [Mate(dev=dev, idle=round(when - seen, 1), holding=held.get(dev, []))
             for dev, seen in store.presence.devs(since=when - PRESENCE_WINDOW,
                                                 in_session=True).items()
             if dev != mine]
    mates.sort(key=lambda mate: (-len(mate["holding"]), mate["idle"], mate["dev"]))
    return Team(me=mine, others=mates)


def _held_by_dev(store: Store, when: float) -> dict[str, list[tuple[str, str]]]:
    """Live leases, grouped by the person behind the actor holding each one.

    A lease and not an assignment: an assignment says a card was chosen for somebody, which
    may have happened an hour before anybody started. What a reader needs in order not to
    collide is what is being TOUCHED, and a live lease is the only fact that says so.
    """
    out: dict[str, list[tuple[str, str]]] = {}
    for lease in store.leases.live(when):
        dev = _dev(lease["actor"])
        if not dev:
            continue
        card = store.tasks.get(lease["task"])
        out.setdefault(dev, []).append((lease["task"], card["title"] if card else ""))
    return out


def _dev(actor: str) -> str:
    try:
        return parse(actor)["dev"] if actor else ""
    except Exception:  # noqa: BLE001 — an id nobody can parse belongs to nobody
        return ""
