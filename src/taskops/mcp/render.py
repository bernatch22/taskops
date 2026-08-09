"""Values → markdown: what every tool result is made of.

v1 had thirty renderers because it also had a management CLI, a statusline and
a channel format. There is one consumer here — an agent reading a tool result —
so there is one shape. Its one companion is `panorama.py`, the board screen,
which was cut from this file at the seam it already had (see that docstring).

Two rules:

* **Every result ends with the pulse line.** That is the whole of layer 3 of the
  context injection: refresh rides along with the call the agent already made.
* **Times are relative** (`3m ago`). Absolute clock formatting would need the
  timezone question answered in the renderer, and `test_architecture.py` keeps
  `strftime` out of everything but the calendar code for exactly that reason.
"""

from __future__ import annotations

from typing import Any

from .._json import as_rows, as_object, as_strings
from ..core.hours import human

BULLET = "◆"


def ago(seconds: float) -> str:
    """`human()` answers "—" under a minute, which reads as "no idea" in a
    timeline. Here that same gap is the truth: it just happened."""
    return f"{human(seconds)} ago" if seconds >= 60 else "just now"


def matches(data: dict[str, Any]) -> str:
    rows = _rows(data.get("matches"))
    if not rows:
        return f"nothing matches {data.get('query')!r}"
    return "\n".join(
        f"{m['id']}  {m['title']}  ({m['state']}{', ' + m['holder'] if m.get('holder') else ''})"
        for m in rows
    )


def plain(data: dict[str, Any]) -> str:
    """Whatever a write verb answered, plus the pulse. Never a bare 'ok'."""
    card = _obj(data.get("card"))
    lines: list[str] = []
    if card:
        lines.append(f"{card.get('id')} {card.get('title')} → {data.get('state', card['status'])}")
    stone = _obj(data.get("milestone"))
    if stone and not card:
        lines.append(f"{BULLET} {stone.get('title')} — {stone.get('status')}")
    for freed in _rows(data.get("freed")):
        lines.append(f"freed {freed['id']} {freed['title']} (worktree kept: {freed['worktree']})")
    for made in _rows(data.get("cards")):
        after = f"  after {', '.join(_strs(made.get('after')))}" if made.get("after") else ""
        lines.append(f"{made['id']}  {made['title']}{after}")
    # A warning a verb wants read, not a status: one block, first line labelled.
    notes = _strs(data.get("notes"))
    if notes:
        lines.append("note: " + "\n".join(notes))
    for merged in ("into", "sha"):
        if data.get(merged):
            lines.append(f"{merged}: {data[merged]}")
    lines.append(pulse(data))
    return "\n".join(lines)


def pulse(data: dict[str, Any]) -> str:
    beat = _obj(data.get("pulse"))
    if not beat:
        return ""
    counts = _obj(beat.get("counts"))
    order = ("doing", "ready", "stalled", "blocked")
    parts = [f"{counts.get(k, 0)} {k}" for k in order if counts.get(k)]
    body = " · ".join(parts) or "nothing open"
    # The mention count is layer 3 doing what a hook was asked to do: it rides
    # on EVERY tool result, so being addressed is found within one call even
    # when nobody opened the board this turn. Nothing when there is nothing —
    # silence is what makes the ✉ mean something when it appears.
    waiting = beat.get("mentions")
    if isinstance(waiting, int) and waiting > 0:
        body += f" · ✉ {waiting} mention{'s' if waiting > 1 else ''} for you"
    return f"─ {BULLET} {beat.get('milestone', 'board')} · {body} ─"


_obj = as_object
_rows = as_rows
_strs = as_strings
