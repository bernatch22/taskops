"""The MCP handshake: the role protocol, and the board as of right now.

`instructions` is the one thing a host loads before the first message of a
session — it is what a system prompt was in v1, without being a second place
where truth lives. Splitting it out of `server.py` keeps that file about the
protocol loop and this one about what a session opens knowing.

Two things ride here, and the ORDER is the design — the BOARD first, the
protocol second. That is not taste: a host TRUNCATES `instructions`, measured
at ~3.1k characters against Claude Code on 2026-08-07, and the first version of
this appended the panorama after 4.6k of protocol, so it was cut off every
single time and the session opened blind. What a session cannot afford to lose
goes first, and the whole thing is kept under the cap. The same reasoning as
`before.py`: an agent reads top-down and may stop early — except here it is the
host that stops reading.

A SessionStart Claude hook was tried for the panorama the same day and removed:
it depends on the host trusting a project settings file and firing an event
nobody controls, while `initialize` happens once per session BY DEFINITION and
the server answering it already holds the board open. One channel, not two.
"""

from __future__ import annotations

from typing import Any

from . import tools, boardview
from .. import _clock
from ..board import Board
from .._errors import TaskopsError
from .._version import __version__

PROTOCOL = "2025-06-18"

OPENING = "THE BOARD RIGHT NOW — already in your context; do not spend a call re-reading it:"

CAP = 2900
"""Total characters `instructions` may spend, panorama INCLUDED. Claude Code
was measured truncating at ~3.1k on 2026-08-07 ("[truncated]" mid-sentence in
the session's own system prompt); 2900 leaves margin under it. The panorama
gets whatever the protocol leaves — and says when it was cut, rather than
trailing off silently the way the host does."""


def hello(board: Board, instructions: str) -> dict[str, Any]:
    room = CAP - len(instructions) - 2
    return {
        "protocolVersion": PROTOCOL,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": "taskops", "version": __version__},
        "instructions": f"{panorama(board, room)}\n\n{instructions}".lstrip(),
    }


def panorama(board: Board, room: int) -> str:
    """What the board is waiting for, right now — the SAME verb and the SAME
    renderer an agent would have called, so this delivers an answer that already
    exists instead of computing a second version of it.

    Silence on any failure: an unreachable board must cost the handshake
    nothing. The tools still work and `taskops_board` is one call away.
    """
    if room < 300:
        return ""  # a protocol that grew past the cap would truncate ITSELF here
    try:
        shown = boardview.board(board.call("board", {}), _clock.now())
    except TaskopsError:
        return ""
    budget = room - len(OPENING) - 2
    if len(shown) > budget:
        shown = f"{shown[: budget - 45]}\n… (cut — taskops_board for all of it)"
    return f"{OPENING}\n\n{shown}"


def describe(tool: tools.Tool) -> dict[str, Any]:
    return {"name": tool.name, "description": tool.description, "inputSchema": tool.schema}
