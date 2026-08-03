"""`taskops attention` — what the board is waiting for, and who has to move.

The verb an orchestrator session opens with. It answers the question the channel used to answer
by interruption — *did anything happen that needs me?* — from state rather than from a push,
which is what makes it work in the deployment the channel never could: a scheduled session on a
server, where nothing is listening because nothing is open.

It writes NOTHING, on purpose, and that is the difference between this and `recover`. A sweep
that fixed what it found would be a second dispatcher running on a timer, and the one rule this
project keeps relearning is that there is exactly one: the orchestrator decides, everything else
reports. `unblock` is the single exception below and it is not a decision — it is the derived
`ready` column catching up with the dependency graph, which every read here already assumes.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from ..contracts.attention import Attention
from ..engine import unblock
from ..engine.attention import waiting_on
from ..storage.milestone import active
from ._project import caller, heartbeat, project
from ._routing import read_remote_first, whoami
from .view import inbox_for

__all__ = ["attention"]


def attention(start: Path | str, *, actor: str = "") -> Attention:
    """The cards that need a decision. Read-only on the BOARD; it does sync first.

    With a remote, the answer comes from the SERVER — the one store every claim, plan and
    close lands in — so it answers for the team by construction. Unreachable, it degrades to
    this machine's cache with a warning, which is the read-side deal everywhere: writes refuse
    to fork the truth, reads refuse to go blind.
    """
    if (answer := read_remote_first(start, "attention",
                                    {"actor": whoami(start, actor)})) is not None:
        return cast("Attention", answer)
    with project(start) as store:
        who = caller(store, actor)["id"]
        heartbeat(store, who)      # a --wait poll IS presence: this dev is here, watching
        unblock(store)
        waiting = waiting_on(store, actor=who)
        mail = len(inbox_for(store, who, mark=False)["messages"])
        # Chapters an agent reported finished. Read from the SAME store as the cards, in the same
        # call, because "the board is waiting on a person" is one question: a milestone sitting in
        # review is the largest thing on a board that only a person can clear, and a sweep that
        # left it out would report a quiet board with a whole chapter waiting to be closed.
        confirm = [m for m in active(store) if m["state"] == "review"]
        return Attention(repo=str(store.root), waiting=waiting, mail=mail, confirm=confirm,
                         quiet=not waiting and not mail and not confirm)
