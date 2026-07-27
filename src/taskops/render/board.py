"""The board as text — the state of the work, column by column.

Read by BOTH a human in a terminal and a model in a context window, which settles most
of the formatting questions: no colour, no box drawing, one glyph per status, counts
rather than bars. What an ACTION returns lives in `results`; the time-window reports live
in `reports`.
"""

from __future__ import annotations

from ..contracts import Board
from ._text import STATUS_MARK, table, truncate

__all__ = ["render_board"]


def render_board(board: Board) -> str:
    """Columns with content only. An empty column is noise on a fifty-task project."""
    parts = [f"# board — {board['total']} task(s), {board['ready']} ready", ""]
    for column in board["columns"]:
        if not column["cards"]:
            continue
        parts += [f"## {STATUS_MARK.get(column['status'], '?')} {column['status']} "
                  f"({len(column['cards'])})", ""]
        rows = [[card["task"]["id"], truncate(card["task"]["title"], 46),
                 str(card["task"]["priority"]),
                 card["lease"]["actor"] if card["lease"] else "—",
                 _counts(card["blocked_by"], card["blocks"], card["commits"])]
                for card in column["cards"]]
        parts += [table(["id", "title", "pri", "who", "deps/commits"], rows), ""]
    return "\n".join(parts)


def _counts(blocked_by: int, blocks: int, commits: int) -> str:
    """`↑2 ↓1 ◆3` — waiting on, blocking, commits. "—" when there is nothing.

    Three zeroes read as data a reader has to parse; one dash reads as "nothing to see",
    which is what it means. The arrows are directional so the two dependency counts cannot
    be mistaken for each other, which numbers alone always are.
    """
    bits: list[str] = []
    if blocked_by:
        bits.append(f"↑{blocked_by}")
    if blocks:
        bits.append(f"↓{blocks}")
    if commits:
        bits.append(f"◆{commits}")
    return " ".join(bits) if bits else "—"
