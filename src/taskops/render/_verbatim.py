"""The two blocks a WRITTEN report carries verbatim: the card's spec, and every word said on it.

Split from `_dossier` because it owns one idea — text that is quoted whole rather than
summarised — and because the density switch lives here rather than in four `if` statements
spread across the renderer.

Why verbatim at all: a report is meant to be read INSTEAD of the git log, and a diff cannot
say what was ASKED or what was DECIDED. The spec is the ask, the comments are the reasoning,
and both are lost the moment they are truncated to one line. The terminal keeps the short
form — nobody wants a screen of quoted essays — so the same projection is printed at two
densities and never forked into two renderers.
"""

from __future__ import annotations

from typing import Literal

from ..contracts import Event, Task
from ._text import truncate

__all__ = ["Detail", "spec_block", "said_block"]

Detail = Literal["brief", "full"]
"""How much of the text survives. `brief` is the terminal, `full` is the file on disk."""


def spec_block(task: Task, detail: Detail) -> list[str]:
    """What was ASKED, quoted whole — `full` only.

    Without it the narration can only describe what was delivered, and "delivered" with
    nothing to compare it against is a changelog, not a report. Quoted with `>` so a spec
    that is itself markdown cannot inject headings into the dossier's own outline.
    """
    spec = task["spec"].strip()
    if detail == "brief" or not spec:
        return []
    return ["", "  **Pedido**", "", *_quote(spec)]


def said_block(mine: list[Event], detail: Detail) -> list[str]:
    """The conversation on one card.

    `brief`: a count and the last line, which is the hand-off note. `full`: every comment
    in order, attributed, whole — that is where the reasoning and the surprises live, and a
    report that drops all but the last one cannot say why anything was done.
    """
    if not mine:
        return []
    if detail == "brief":
        text = str(mine[-1]["body"].get("text", ""))
        return [f"  {len(mine)} comment(s) · last: {truncate(text, 120)}"]
    out = ["", f"  **{len(mine)} comment(s)**"]
    for event in mine:
        out += ["", f"  **{event['actor']}**:", "", *_quote(str(event["body"].get("text", "")))]
    return out


def _quote(text: str) -> list[str]:
    """Every line of `text` as an indented blockquote, blank lines included.

    Blank lines carry the `>` too: a markdown blockquote broken by a bare empty line becomes
    two quotes with a paragraph between them, and a multi-paragraph spec would stop reading
    as one quoted thing.
    """
    return [f"  > {line}".rstrip() for line in text.strip().splitlines()]
