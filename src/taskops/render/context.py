"""A context slice as text: the objective, then the invariants, then the decisions.

That order is the reading order, not an alphabet. An invariant is the one kind a worker may
not weigh against anything else, so it comes before the decisions it constrains and after the
objective it exists to protect.

Pure text, like everything in `render/`, which is what lets the same three lists serve the CLI
and the MCP reply without either surface growing its own formatter — the shape has been
settling in `transports/cli/commands/context.py` and this is where it lands.
"""

from __future__ import annotations

from ..contracts.context import ContextSlice, Fact

__all__ = ["render_context"]


def render_context(view: ContextSlice) -> str:
    lines = ["# objective", _line(view["objective"]) if view["objective"] else "(none set)",
             "", "# invariants"]
    lines += [_line(f) for f in view["invariants"]] or ["(none)"]
    lines += ["", "# decisions"]
    lines += [_line(f) for f in view["decisions"]] or ["(none)"]
    return "\n".join(lines)


def _line(fact: Fact) -> str:
    """The id first and truncated to eight: it is what `context retire` takes, and a full
    event hash on every line would push the text — the part anybody reads — off the screen."""
    scope = ", ".join(fact["labels"] + fact["files"])
    tail = f"  [{scope}]" if scope else ""
    return f"{'~' if fact['retired'] else '·'} {fact['id'][:8]}  {fact['text']}{tail}"
