"""A specialist agent, as the board understands it.

taskops is the REGISTRY and the ROUTER; the host session is the only thing that ever invokes
an agent. So what a spec has to carry is not "how to run this" but the two facts a board can
act on — which cards are this specialist's (`labels`) and what it may edit (`files`) — plus
enough of the original file to hand back to Claude Code unchanged.

`text` is the file VERBATIM, and that is deliberate. Materialisation re-emits the agent into
`.claude/agents/` by stripping the two taskops-only keys out of this text rather than
re-serialising a parsed model: a round trip through a hand-rolled writer would quietly drop
every frontmatter key this parser does not happen to know about, and Claude Code's key set is
not ours to freeze.
"""

from __future__ import annotations

from typing import TypedDict

__all__ = ["AgentSpec"]


class AgentSpec(TypedDict):
    """One `*.md` agent file, parsed. Flat, like every other contract."""

    name: str
    """The registry key. A repo file overrides a plugin file of the same name."""

    description: str

    labels: list[str]
    """Which cards belong to this specialist. Empty means "no opinion" — such an agent is
    never routed to and never fences anybody out of anything."""

    files: list[str]
    """Its edit surface, as globs. A hint for humans and for a future guard; nothing in this
    card enforces it, and a spec that claimed otherwise would be a lie in a contract."""

    path: str
    """Where it was read from — every refusal and every warning names it."""

    text: str
    """The file as it sits on disk, frontmatter included."""
