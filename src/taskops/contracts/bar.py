"""What a Claude Code STATUS LINE gets to say about the board — the bottom bar, as a value.

A different projection from `Attention` and deliberately so. `attention` answers "what should
the orchestrator do next", is allowed to reach the server, and is read once a turn. This is read
on every keystroke-ish update Claude Code debounces, so it is bounded by what one local sqlite
answers in a few milliseconds and by what fits on one row of a terminal.

`local` is the field that would not exist if the two were merged, and it is the reason this
projection is worth having: on a shared board the bar is showing a CACHE — a teammate's claim
lands here on the next sync and not the instant they make it — and a bar that looked identical
either way would quietly promise a liveness it does not have.
"""

from __future__ import annotations

from typing import TypedDict

__all__ = ["Bar", "Holding"]


class Holding(TypedDict):
    """A card this actor has a live lease on — what they are working on right now."""

    id: str
    title: str
    status: str


class Bar(TypedDict):
    objective: str
    """What the project is for, as text. Here rather than left to the greeting because a greeting
    scrolls away: this is the row that is still on screen an hour later, which is the only place
    a standing fact can actually stand."""

    board: str
    """The board's name — the project directory, which is what a person calls it out loud."""
    local: bool
    """True when nothing is shared: no `remote.json`, so this disk is the whole truth."""

    holding: list[Holding]
    waiting: dict[str, int]
    """`{move: count}` over `contracts.attention.MOVES`. Counted and not listed: a bar has one
    row, and which card needs dispatching is a question with a whole verb behind it."""
    mail: int
