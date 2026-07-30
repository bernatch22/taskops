"""`taskops attention` — what the board is waiting for, and who has to move.

The verb an orchestrator session opens with. It answers the question the channel used to answer
by interruption — *did anything happen that needs me?* — from state rather than from a push,
which is what makes it work in the deployment the channel never could: a scheduled session on a
server, where nothing is listening because nothing is open.

It writes NOTHING, on purpose, and that is the difference between this and `recover`. A sweep
that fixed what it found would be a second dispatcher running on a timer, and the one rule this
project keeps relearning is that there is exactly one: the orchestrator decides, everything else
reports. `unblock` is the single exception below and it is not a decision — it is the derived
`ready` column catching up with the dependency graph, which every read here already assumes.
"""

from __future__ import annotations

from pathlib import Path

from ..contracts.attention import Attention
from ..engine import unblock
from ..engine.attention import waiting_on
from ._project import project

__all__ = ["attention"]


def attention(start: Path | str) -> Attention:
    """The cards that need a decision. Read-only, and safe to run in a loop."""
    with project(start) as store:
        unblock(store)
        waiting = waiting_on(store)
        return Attention(repo=str(store.root), waiting=waiting, quiet=not waiting)
