"""What a recovery freed, written for somebody staring at a stuck board.

The leftovers are the point of this render. A card that came back with no explanation looks like a
card nobody started, and the next agent rewrites from zero the file sitting in a directory two levels
down — which is what nearly happened the day this was needed.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ._text import table

__all__ = ["render_recover", "RecoveredLike"]


class StuckLike(Protocol):
    @property
    def task(self) -> str: ...
    @property
    def actor(self) -> str: ...
    @property
    def silent_for(self) -> float: ...
    @property
    def commits(self) -> int: ...
    @property
    def leftovers(self) -> Sequence[str]: ...


class RecoveredLike(Protocol):
    """Structural, so `render/` never imports `usecases` — an invariant test enforces it."""

    @property
    def released(self) -> Sequence[StuckLike]: ...
    @property
    def alive(self) -> Sequence[str]: ...


def render_recover(result: RecoveredLike) -> str:
    if not result.released:
        return _nothing(result)
    rows = [[s.task, s.actor, f"{int(s.silent_for // 60)}m",
             str(s.commits) if s.commits else "—",
             f"{len(s.leftovers)} file(s)" if s.leftovers else "—"]
            for s in result.released]
    parts = [f"# recovered {len(result.released)} card(s)", "",
             table(["task", "was held by", "silent", "commits", "uncommitted"], rows),
             "", "They are `ready` and unassigned again — dispatch or claim them normally."]
    salvage = [s for s in result.released if s.leftovers]
    if salvage:
        parts += ["", "⚠ UNCOMMITTED work survives — read it before redoing the task:"]
        parts += [f"  {s.task}: {', '.join(s.leftovers)}" for s in salvage]
    if result.alive:
        parts += ["", f"Still reporting, left alone: {', '.join(result.alive)}"]
    return "\n".join(parts)


def _nothing(result: RecoveredLike) -> str:
    """Nothing stuck is the GOOD outcome, and it has to read like one rather than like a failure."""
    if result.alive:
        return ("Nothing to recover — every worker is still reporting: "
                + ", ".join(result.alive))
    return "Nothing to recover — no live claims at all."
