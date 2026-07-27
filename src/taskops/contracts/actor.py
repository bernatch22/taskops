"""Who did it — the identity that outlives a session.

The "50 First Dates" problem in one type: a Claude Code session is anonymous and
gone tomorrow, so anything it writes has to be attributed to something that is
neither. An actor id is `dev:<name>` or `agent:<dev>/<name>`, and the second half
of the agent form is what makes a hundred agents belonging to four developers
legible on one board — every agent answers to a human by construction.

Format handling lives in `engine.identity`, not here: this layer is types only.
"""

from __future__ import annotations

from typing import TypedDict

from .._types import ActorKind

__all__ = ["Actor"]


class Actor(TypedDict):
    """A developer or one of their agents."""

    id: str
    """`dev:berna` or `agent:berna/polecat-1`. The wire form, and what the event
    log stores — a nested object would make every event three lines of JSON."""

    kind: ActorKind
    dev: str
    """The human accountable for this actor. For a dev, itself."""
