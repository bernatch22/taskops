"""The MCP handshake: the role protocol, and the board as of right now.

`instructions` is the one thing a host loads before the first message of a
session — it is what a system prompt was in v1, without being a second place
where truth lives. Splitting it out of `server.py` keeps that file about the
protocol loop and this one about what a session opens knowing.

Two things ride here, and the ORDER is the design: the protocol first (it is
what makes the rest legible), then the panorama. A SessionStart Claude hook was
tried for the panorama on 2026-08-07 and removed the same day: it depends on
the host trusting a project settings file and firing an event nobody controls,
while `initialize` happens once per session BY DEFINITION and the server
answering it already holds the board open. One channel, not two.
"""

from __future__ import annotations

from typing import Any

from . import tools, render
from .. import _clock
from ..board import Board
from .._errors import TaskopsError
from .._version import __version__

PROTOCOL = "2025-06-18"

OPENING = "THE BOARD, AS OF THIS SESSION'S START — so the first turn already knows it:"


def hello(board: Board, instructions: str) -> dict[str, Any]:
    return {
        "protocolVersion": PROTOCOL,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": "taskops", "version": __version__},
        "instructions": f"{instructions}\n\n{panorama(board)}".rstrip(),
    }


def panorama(board: Board) -> str:
    """What the board is waiting for, right now — the SAME verb and the SAME
    renderer an agent would have called, so this delivers an answer that already
    exists instead of computing a second version of it.

    Silence on any failure: an unreachable board must cost the handshake
    nothing. The tools still work and `taskops_board` is one call away.
    """
    try:
        return f"{OPENING}\n\n{render.board(board.call('board', {}), _clock.now())}"
    except TaskopsError:
        return ""


def describe(tool: tools.Tool) -> dict[str, Any]:
    return {"name": tool.name, "description": tool.description, "inputSchema": tool.schema}
