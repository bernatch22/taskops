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

from .task import Task

__all__ = ["Move", "Waiting", "Attention", "MOVES"]

Move = Literal["verify", "resume", "dispatch", "specless", "stalled"]

MOVES: tuple[Move, ...] = ("verify", "resume", "dispatch", "specless", "stalled")
"""In the order an orchestrator should act on them, and that order is a claim.

Finishing beats starting: a card in `review` is minutes from `done` and closing it may unblock
three others, while a `dispatch` adds a fourth thing in flight. `specless` and `stalled` come
last because neither is the orchestrator's to fix — they are the two that need a person.
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
    quiet: bool
    """True when nothing is waiting. Named rather than left to `not waiting`, because an empty
    board and a board whose every card is in flight are the same list and different situations,
    and the renderer says so differently."""
