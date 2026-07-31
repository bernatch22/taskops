"""Telling the people a close just unblocked.

The gap a question found: when dev2 closes B and card C becomes `ready`, the STATE is correct
instantly — `unblock` runs inside the same write, in the one store everybody reads. What is
missing is that nobody tells dev1. C sits pickable and invisible until dev1's next turn asks.

The information exists and is thrown away. The close already computes exactly which cards it
freed and hands them back to its caller; that is a fact about somebody ELSE's work, arriving
in the one session that does not need it. So it is turned into a mention, which is the channel
this system already has: a message reaches an agent on its very next tool call, through the
`PostToolUse` hook, without it having to ask.

**Only somebody with a claim on the news.** A card nobody is waiting for is a card that
belongs in the pool, and mentioning the whole team every time a dependency clears would train
everyone to ignore the inbox — which costs more than the notification is worth.
"""

from __future__ import annotations

from ..contracts import Task
from ..engine import parse, record
from ..storage import Store

__all__ = ["announce_unblocked"]


def announce_unblocked(store: Store, freed: list[Task], closer: str) -> list[str]:
    """Mention whoever was waiting on each freed card. Returns who was told."""
    told: list[str] = []
    for card in freed:
        who = _waiting_for(card, closer)
        if not who:
            continue
        record(store, task=card["id"], actor=closer, kind="message",
               body={"text": f"{card['id']} is ready — its dependencies just closed. "
                             f"“{card['title']}”",
                     "mentions": [who]})
        told.append(who)
    return told


def _waiting_for(card: Task, closer: str) -> str:
    """Who, if anybody, is owed this news.

    The assignee first: a card handed to somebody is theirs, and them learning it is pickable
    is the whole point. Otherwise the person who PLANNED it — they wrote it and are the one
    likeliest to be waiting on the tree it belongs to.

    Never the closer: telling somebody about a consequence of their own call is noise, and
    they already got it in the reply. Never an `agent:` id either — an agent that finished its
    card is gone by the time this fires, so the message would land in an inbox nobody opens.
    The developer behind it is the one still there.
    """
    for candidate in (card["assignee"], card["created_by"]):
        person = _person(candidate)
        if person and person != _person(closer):
            return person
    return ""


def _person(actor: str) -> str:
    """`agent:ana/w1` and `dev:ana` are one person; a message goes to the person."""
    try:
        return f"dev:{parse(actor)['dev']}" if actor else ""
    except Exception:  # noqa: BLE001 — a legacy id is not worth refusing a close over
        return ""
