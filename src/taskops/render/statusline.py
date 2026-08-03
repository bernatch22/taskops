"""The bottom bar — one row of a terminal, rebuilt hundreds of times per session.

Claude Code renders a status line in **its own row above** the built-in footer badges; it does not
replace them, so `⏵⏵ bypass permissions on` stays where it is whatever this prints.

**It said `-- INSERT --` and that was a mistake.** The reasoning was that an eye going to the
bottom of the screen should find the mode and the board in one place — but Claude Code already
prints the vim mode in the very next row, so the bar spent its most valuable characters saying
something already on screen one line below. Repeating what the harness says is worse than saying
nothing: it costs the width AND it makes the row look like chrome.

What went there instead is the **objective** — the one fact whose entire value is being in your eye
while you decide something else, and the only thing here that no other surface keeps visible. The
session greeting says it once and scrolls away; the board says it in a browser nobody has open.

**Ordered by how fast it decays.** What you are holding changes when you claim; what is waiting
changes when a teammate moves; the board name never changes. So the volatile end leads, and a
narrow terminal truncates the part that was going to be the same tomorrow.

Pure, like everything in this package: a value and the harness payload in, a string out. That is
what makes a bar testable at all — the alternative is reading a screenshot.
"""

from __future__ import annotations

from typing import Any

from ..contracts.attention import MOVES
from ..contracts.bar import Bar

__all__ = ["render_statusline"]

DIM, OFF = "\x1b[2m", "\x1b[0m"
AMBER, LIME, BLUE, RED = "\x1b[33m", "\x1b[32m", "\x1b[34m", "\x1b[31m"

GAP = f"{DIM}  ·  {OFF}"
TITLE, GOAL = 28, 40

SAYS: dict[str, tuple[str, str]] = {
    "verify": ("to review", BLUE),
    "dispatch": ("to hand out", LIME),
    "land": ("to land", AMBER),
    "resume": ("stranded", AMBER),
    "specless": ("with no spec", DIM),
    "stalled": ("stuck", RED),
}
"""Board vocabulary, translated — the same rule the session greeting follows. A bar is allowed
to be terse, never cryptic: `5 to hand out` is as short as `5 dispatch` and means something to
somebody who has not read the manual."""


def render_statusline(bar: Bar, payload: dict[str, Any]) -> str:
    """The row. `payload` is the JSON Claude Code writes to a status line's stdin."""
    parts = [_north(bar), _holding(bar), _waiting(bar), _where(bar), _context(payload)]
    return GAP.join(part for part in parts if part)


def _north(bar: Bar) -> str:
    """What this project is for, first on the row.

    Cut hard and deliberately: this is the one segment that would grow with somebody's prose, and
    a bar whose left end pushes what is WAITING off the right of the screen has inverted its own
    priorities. Truncated it is still the reminder; absent it is nothing.
    """
    said = _short(bar.get("milestone") or "", GOAL)
    return f"{DIM}◎{OFF} {said}" if said else ""


def _holding(bar: Bar) -> str:
    """What is under this person's hands right now — the first thing the bar owes them."""
    held = bar["holding"]
    if not held:
        return ""
    first = held[0]
    more = f"{DIM} +{len(held) - 1}{OFF}" if len(held) > 1 else ""
    # The id WHOLE: it is nine characters, and the point of putting it on screen is that
    # somebody can read it straight into `taskops tasks show`. A shortened one cannot be.
    return f"{AMBER}◐ {first['id']}{OFF} {_short(first['title'], TITLE)}{more}"


def _waiting(bar: Bar) -> str:
    """What the board wants, counted per move, in the order `MOVES` already argued for.

    Sorted by that order and not by size: the point of the ordering is that closing a review
    can unblock three cards while a dispatch adds a fourth thing in flight, and a bar that
    re-sorted by count every time something moved would also be a bar that never sits still.
    """
    said = []
    for move in MOVES:
        count, seen = bar["waiting"].get(move, 0), SAYS.get(move)
        if count and seen:
            said.append(f"{seen[1]}{count}{OFF} {seen[0]}")
    if bar["mail"]:
        said.append(f"{DIM}✉{OFF} {bar['mail']}")
    return f"{DIM},{OFF} ".join(said)


def _where(bar: Bar) -> str:
    """The board, and whether this row is the truth or a copy of it.

    `cached` is the whole reason this segment exists. On a shared board the bar reads a replica
    that syncs when something calls taskops, so a teammate's claim lands here late — and a bar
    that looked identical either way would promise a liveness it does not have.
    """
    kind = "local" if bar["local"] else "shared, cached"
    return f"{DIM}{bar['board']} ({kind}){OFF}"


def _context(payload: dict[str, Any]) -> str:
    """Context used, and nothing until it is worth knowing.

    Silent under half: a number that is on screen from the first prompt is a number nobody
    reads by the time it matters. It turns amber at 70 and red at 90, which is the only place
    on this bar where a colour is a warning rather than a category.
    """
    window: dict[str, Any] = payload.get("context_window") or {}
    used = int(window.get("used_percentage") or 0)
    if used < 50:
        return ""
    tone = RED if used >= 90 else AMBER if used >= 70 else DIM
    return f"{tone}{used}% ctx{OFF}"


def _short(text: str, width: int) -> str:
    clean = " ".join(text.split())
    return clean if len(clean) <= width else clean[: width - 1].rstrip() + "…"
