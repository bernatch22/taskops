"""What a session is handed the moment it opens — the reason it knows who it is.

A session used to start knowing only what it HELD, which for a fresh conversation is nothing,
and the injection ended with "Run taskops_next to claim one." That sentence is why two real
sessions did the work themselves and left the cards dead: the first thing the main agent read
told it to be a worker, so it was one, and nobody was left to verify or dispatch anything.

The role is not a preference and not a prompt somebody remembers to write. `SessionStart` fires
for the MAIN conversation only — sub-agents never see it — so the event itself is the proof of
which one this is. That makes "you are the orchestrator" a fact the transport can state.
"""

from __future__ import annotations

from typing import TypedDict

from .attention import Waiting
from .context import ContextSlice
from .event import Event
from .lease import Lease
from .team import Team

__all__ = ["Opening"]


class Opening(TypedDict):
    """The whole first screen: who, what the project has decided, and what is waiting."""

    actor: str
    session: str

    context: ContextSlice
    """The standing objective, invariants and decisions. Injected HERE rather than left for
    the agent to fetch, because a session that has to remember to ask about the project's
    constraints is a session that will edit against one of them before it does."""

    waiting: list[Waiting]
    """`attention`, verbatim. The orchestrator's first question is always "what needs a
    decision", so the answer arrives before the question."""

    held: list[Lease]
    """Cards this actor still holds — a resumed session, or leases that outlived a crash."""

    messages: list[Event]

    team: Team
    """Who else is connected, and what they are holding. The one thing here that is not about
    this session: without it two sessions on one board each behave as though they were alone,
    which is how a card got implemented twice and a review got started by two devs at once."""
