"""Text primitives. Pure functions of strings — no I/O anywhere in `render/`.

That purity is enforced (`tests/architecture`) and it is what lets the same renderer
serve the CLI, the MCP reply and the web UI's markdown export: a rendering bug is
reproducible from a literal dict with no database in sight.
"""

from __future__ import annotations

from .._clock import now

__all__ = ["ago", "span", "bullet", "table", "truncate", "STATUS_MARK"]

STATUS_MARK = {"backlog": "·", "ready": "○", "claimed": "◐", "in_progress": "●",
               "blocked": "✕", "review": "◆", "done": "✓", "cancelled": "—"}
"""One glyph per status, so a board scans vertically without reading words.

ASCII-ish and deliberately not emoji: this is read in a terminal by a human and in a
context window by a model, and emoji cost several tokens each for the same information.
"""


def ago(ts: float, *, at: float | None = None) -> str:
    """`1 800 000 042.0` -> "3m ago". Coarse on purpose.

    Nobody acts differently on 187 versus 190 seconds, and a precise duration invites a
    reader to compare two of them — which is a comparison between two clocks that may not
    agree, since these timestamps come from different machines.
    """
    seconds = max(0.0, (now() if at is None else at) - ts)
    return f"{span(seconds)} ago" if seconds >= 60.0 else "just now"


def span(seconds: float) -> str:
    """`5400.0` -> "1h". A DURATION, where `ago` is a distance from now.

    The same coarseness and the same arithmetic, which is why `ago` is written in terms of
    it: two rounding rules for two ways of printing the same number is how a card ends up
    saying it took 2h beside a claim that says 3h ago.
    """
    for size, unit in ((86400.0, "d"), (3600.0, "h"), (60.0, "m")):
        if seconds >= size:
            return f"{int(seconds // size)}{unit}"
    return "under a minute"


def truncate(text: str, limit: int) -> str:
    """One line, at most `limit` characters. Collapses newlines first.

    A spec's first line is often a sentence that continues, and pasting the raw newline
    into a table cell breaks the table for every row after it.
    """
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def bullet(lines: list[str], *, indent: int = 0) -> str:
    prefix = " " * indent + "- "
    return "\n".join(prefix + line for line in lines)


def table(headers: list[str], rows: list[list[str]]) -> str:
    """A markdown table, or "" for no rows.

    Empty rather than a header with nothing under it: a reader shown an empty table has
    to work out whether the query failed or the answer is genuinely nothing, and the
    caller knows which and can say so in a sentence.
    """
    if not rows:
        return ""
    head = "| " + " | ".join(headers) + " |"
    rule = "|" + "|".join("---" for _ in headers) + "|"
    body = ["| " + " | ".join(cell for cell in row) + " |" for row in rows]
    return "\n".join([head, rule, *body])
