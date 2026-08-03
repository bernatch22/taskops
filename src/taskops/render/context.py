"""A context slice as text — the blocks, plus the OBJECTIVES the injection has no room for.

The blocks live in `_blocks` because three surfaces render them (this, the MCP reply, the
SessionStart injection) and none of the three may own the shape. What is here is the part only a
person reads: who on the team is working towards what, which is the question "who do I hand this
card to" and is asked at a terminal rather than by an agent mid-task.

**Rules and decisions are the same SORT, split by their scope, and the split is why the fourth
sort could go.** A decision with no `labels` and no `files` reaches every card — that is a rule,
mechanically — and one with a scope reaches only the cards that share it. Printed as one flat
list they read identically, which made the strongest facts on a board look like the weakest.
"""

from __future__ import annotations

from ..contracts.slice import ContextSlice
from ._blocks import chapters_block, dev, fact_line, project_block

__all__ = ["render_context"]


def render_context(view: ContextSlice) -> str:
    """The project's rules, then the chapter(s) with their facts, then who is on what.

    Never empty: a board that has stated nothing and opened no chapter still answers with the
    block that says so and names the command that fixes it.
    """
    lines = [*project_block(view), *chapters_block(view), *_who(view)]
    return "\n".join(lines).rstrip() or "\n".join(chapters_block(view)).rstrip()


def _who(view: ContextSlice) -> list[str]:
    """Everybody's objective, one line each — the OVERVIEW only.

    A card's slice carries one objective (`yours`, printed under its chapter) and that is
    deliberate: the slice grows by one whether three people are on the board or thirty. This list
    is the other question, and it is only ever asked by somebody deciding who to dispatch to.
    """
    theirs = view["objectives"]
    if not theirs or view["milestone"]:
        return []
    # An UNOWNED objective is marked rather than dropped. It cannot be written any more (`state`
    # refuses one), but a board written before milestones has them, and a fact that vanishes
    # because a version changed is the one thing an append-only log must never do.
    return ["## Who is working towards what",
            *[f"  {dev(f['owner']) or 'project':<10} {fact_line(f)}" for f in theirs], ""]
