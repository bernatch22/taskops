"""What the board is WAITING FOR — the orchestrator's turn, as a value.

This is the projection that replaced a notification channel. Board events used to be pushed
into an open session so it could react to them; every one of those reactions turned out to be
idempotent and derivable from state, which means the state can be asked instead of the event
delivered. A card sitting in `review` with nobody verifying it needs a verifier whether the
event arrived one second ago or the session opened this morning.

Derived like every other projection here, so it cannot drift and needed no migration.
"""

from __future__ import annotations

from typing import Literal, TypedDict

from .milestone import Milestone
from .task import Task

__all__ = ["Move", "Waiting", "Attention", "MOVES"]

Move = Literal["land", "verify", "resume", "dispatch", "specless", "stalled"]

MOVES: tuple[Move, ...] = ("land", "verify", "resume", "dispatch", "specless", "stalled")
"""In the order an orchestrator should act on them, and that order is a claim.

`land` leads because it is the only group about work that is FINISHED and still invisible: a
board reported a hundred and eighteen cards done with the trunk on its seed commit, which is
the one thing a board exists not to do. Then finishing beats starting — closing a review may
unblock three cards, while a dispatch adds a fourth thing in flight. `specless` and `stalled`
come last because neither is the orchestrator's to fix; they need a person.
"""


class Waiting(TypedDict):
    """One card and the single next move on it, said in the imperative."""

    task: Task
    move: Move
    why: str
    """Why THIS card is in THIS group, from its own state — not the group's description. A
    reader who disagrees with the move needs the fact it was derived from, not a restatement."""


class Attention(TypedDict):
    repo: str
    waiting: list[Waiting]

    confirm: list[Milestone]
    """Milestones an agent reported finished, waiting for a person to verify or send back.

    A separate list from `waiting` because every entry there is a CARD, and a reader that had to
    tell them apart by shape would eventually not. It is the same kind of fact though — something
    only a person can clear — which is why it belongs in this projection at all rather than in a
    notification nobody is listening for.
    """

    mail: int
    """Messages addressed to this actor and not yet delivered to it.

    Here rather than left to the inbox because of the deployment with NO channel, which is the
    one this verb was written for: a routed review reaches its dev as a directed message, and a
    sweep that reported only card moves would leave the one thing somebody chose FOR you as the
    one thing polling could not see. Counted, never consumed — delivery is a fact about the
    agent having read something, and only the agent's own read may assert it."""
    quiet: bool
    """True when nothing is waiting. Named rather than left to `not waiting`, because an empty
    board and a board whose every card is in flight are the same list and different situations,
    and the renderer says so differently."""
