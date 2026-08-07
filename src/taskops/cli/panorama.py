"""The board, delivered ONCE at the start of a session.

Split from `claude.py` along the line the hook itself draws: that file answers
*who is this turn for and may we look*, this one answers *what does a session
open knowing*. Same contract as its sibling — read, never write; silence and
exit 0 on any failure; deleting it costs nothing but the first turn.

Berna asked for this on 2026-08-07: a session used to open blind and spend its
first move on `taskops_board`, which is the one call the protocol already says
to make. It is the same narrowing as MENTIONS.md §9 and not a widening of it —
what is delivered here is an answer that ALREADY EXISTS, produced by the same
verb and the same renderer an agent would have called. A hook that computed its
own summary would be a second version of the board, and a second version is how
v1 came to disagree with itself.
"""

from __future__ import annotations

from pathlib import Path

from .. import _clock
from ..mcp import render
from ..board import open_board

TIMEOUT = 2.0  # a slow board must cost the session's first turn nothing


def board(root: Path, who: str) -> str:
    """The panorama for `who`, or "" when it is not theirs to see.

    Only a `dev:`. `board` opens with `live.renew(actor)` — right for a call the
    actor typed, fatal on somebody else's behalf: renewing a worker's lease from
    a hook would keep a dead worker's card out of STALLED, which is a stored
    `doing` grown back through the side door (MENTIONS.md §9e). A dev holds no
    leases at all — the role wall forbids it — so renewing one touches no mutex
    and only stamps presence, which is true anyway: the human just arrived.
    """
    if not who.startswith("dev:"):
        return ""
    opened = open_board(root, who, TIMEOUT)
    try:
        return render.board(opened.call("board", {}), _clock.now())
    finally:
        opened.close()
