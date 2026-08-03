"""A context slice as text: the objective, then the decisions, then the notes.

That order is the reading order, not an alphabet. The objective is what everything else exists
to serve, so it leads; a decision is settled and constrains what a worker may reconsider, so it
comes next; a note is standing and neither, so it comes last.

Pure text, like everything in `render/`, which is what lets the same three lists serve the CLI
and the MCP reply without either surface growing its own formatter — the shape has been
settling in `transports/cli/commands/context.py` and this is where it lands.
"""

from __future__ import annotations

from ..contracts.context import ContextSlice, Fact

__all__ = ["render_context"]


def render_context(view: ContextSlice) -> str:
    """The project's north first, then yours, then the rules, then anything else standing.

    That order is the argument: a worker reads top to bottom and the first thing it learns is
    what the TEAM is for. Its own objective second, because "I am on the parser this week" only
    means something against a north somebody already stated.
    """
    lines = ["# objective", *_goals(view)]
    if view["yours"]:
        lines += ["", f"# yours ({_dev(view['yours']['owner'])})", _line(view["yours"])]
    lines += ["", "# decisions"]
    lines += [_line(f) for f in view["decisions"]] or ["(none)"]
    if view["notes"]:
        lines += ["", "# notes", *[_line(f) for f in view["notes"]]]
    return "\n".join(lines)


def _goals(view: ContextSlice) -> list[str]:
    """The objectives, the project's first and each dev's under it.

    A SLICE carries one — that is what a worker reads — so when `objectives` holds nothing more
    than the one already shown, this prints one line and looks exactly as it always did. The
    list appears only where there is something a single line would have hidden, which is the
    overview: who is on what, when you are deciding who to hand a card to.
    """
    theirs = [f for f in view["objectives"]
              if f["owner"] and f is not view["objective"] and f is not view["yours"]]
    if not view["objective"] and not theirs:
        return ["(none set)"]
    lines = [_line(view["objective"])] if view["objective"] else ["(none set — project-wide)"]
    return lines + [f"  {_dev(f['owner'])}: {_line(f)}" for f in theirs]


def _dev(owner: str) -> str:
    return owner.partition(":")[2] or owner


def _line(fact: Fact) -> str:
    """The id first and truncated to eight: it is what `context retire` takes, and a full
    event hash on every line would push the text — the part anybody reads — off the screen."""
    scope = ", ".join(fact["labels"] + fact["files"])
    tail = f"  [{scope}]" if scope else ""
    if fact["horizon"]:
        tail += f"  by {fact['horizon']}"
    return f"{'~' if fact['retired'] else '·'} {fact['id'][:8]}  {fact['text']}{tail}"
