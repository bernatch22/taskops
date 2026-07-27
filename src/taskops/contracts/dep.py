"""The dependency edge. Two ids and a direction — that is genuinely all of it.

Direction is fixed and worth stating once, because every reader gets it backwards
otherwise: `task` must finish BEFORE `blocks` can start. So `deps` rows are read
one way to ask "what am I waiting for" (`WHERE blocks = me`) and the other way to
ask "who is waiting on me" (`WHERE task = me`), and both are one indexed lookup.

Kept as a separate edge table rather than a `blocked_by` list on the task because
the graph is queried from both ends, and a JSON list can only be read from one.
"""

from __future__ import annotations

from typing import TypedDict

__all__ = ["Dep"]


class Dep(TypedDict):
    """`task` blocks `blocks`."""

    task: str
    blocks: str
