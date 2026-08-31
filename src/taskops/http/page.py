"""The page door — `handler._static`, moved whole when the git smart-HTTP
door (`gitpack.py`) pushed the handler past its ≤200-line budget: this is the
one GET branch that is a policy of its own (visibility, the repo fact, the
410) rather than a route, so it is the cohesive cut. The bytes themselves are
still `static.py`'s; the credential is still the handler's ONE `_credential`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import rpc, static
from .._errors import TaskopsError

if TYPE_CHECKING:
    from .handler import Handler


def answer(handler: Handler, board: str, rest: str) -> None:
    """The page — at the board's own root since tk-32d2ba, and still at
    /ui/, the 0.5.0 address (kept: links were pasted). A WINDOW serves
    its bundle to whoever reaches the port, unchanged. A serve-mode HOST
    serves the SAME packaged bundle for a board
    whose own repository is here (`repos.backed` — the fact, never a diff),
    behind the credential /rpc asks for: public board, anonymous READ;
    private board, the join refusal. The 410 comes BEFORE the credential on
    purpose — it says nothing about the board a login would guard, and the
    no-git sentence predates keys on this door. A GET here runs no verb,
    so an anonymous page load writes nothing — no presence row (§11)."""
    if handler.mounts.ui is not None:
        handler._send(*static.answer(handler.mounts.ui, rest))  # noqa: SLF001
        return
    try:
        handler.mounts.check(board)
        if not handler.mounts.repos.backed(board):
            handler._send(*static.answer(None, rest))  # noqa: SLF001
            return
        handler._credential(board, "read")  # noqa: SLF001
    except TaskopsError as err:
        handler._fail(rpc.status_for(rpc.failure(err)), err)  # noqa: SLF001
        return
    handler._send(*static.answer(static.PACKAGED, rest))  # noqa: SLF001
