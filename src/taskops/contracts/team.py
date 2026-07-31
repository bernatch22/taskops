"""Who else is here, and what they have their hands on.

The question a session cannot answer from its own state and pays for by colliding: two devs
picking up neighbouring cards, two agents editing one file, a review started twice. The board
already knows — presence rides every heartbeat and a lease names its holder — but nothing
assembled the answer, so every session behaved as if it were alone on the project.

It is a BRIEF, not a feed. Names and card titles, no history: enough to not collide, short
enough that every session can be handed it before anybody types.
"""

from __future__ import annotations

from typing import TypedDict

__all__ = ["Mate", "Team"]


class Mate(TypedDict):
    """One developer who is connected, and the cards their agents are holding."""

    dev: str
    """Bare, without the `dev:` prefix — a person, not an actor id. A dev and their agents are
    one entry: `agent:ana/w1` holding a card is `ana` working on it, and splitting them would
    tell a reader that four strangers are busy when one colleague is."""

    idle: float
    """Seconds since this dev's last signal. Rendered rather than judged here — "connected" is
    a window (`routereview.PRESENCE_WINDOW`), and a reader deserves to see the edge of it."""

    holding: list[tuple[str, str]]
    """(card id, title) per card this dev's actors hold a live lease on. Empty means connected
    and free, which is the state the orchestrator most wants to know about."""


class Team(TypedDict):
    """The brief, with `me` separated so a session is never told it might collide with itself."""

    me: str
    others: list[Mate]
