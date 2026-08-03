"""Which chapter a new fact joins.

Split from `context` on its budget, and the split names a real question: that module records a
fact, and this answers the one thing about it that nobody may be asked. Several milestones are
active at once, so "which one does this belong to" is real — and it is not the caller's to answer.
A fact filed under the wrong chapter reaches the wrong cards and nothing anywhere says so, which
is the shape of every bug this project keeps writing rules about.
"""

from __future__ import annotations

from ..storage import Store
from ..storage.context import facts
from ..storage.milestone import active
from ._whose import dev_of, winner

__all__ = ["chapter_for"]


def chapter_for(store: Store, owner: str) -> str:
    """Which active chapter a new fact joins, or "" when the board has none.

    A DEV's own fact joins the chapter their own objective is in — that is what they are working
    under, and it is the one answer nobody has to guess. With no objective of their own, and for
    the project's facts, it is the OLDEST active chapter: the one that has been running longest is
    the one a new rule is overwhelmingly about, and picking the newest would attach today's
    decision to something started this morning.

    `""` is legal and means "in force everywhere", which is what a board with no chapter yet needs
    — `plan` refuses there, so the only facts that can arrive are the ones somebody wrote before
    opening one, and losing them would be worse than filing them loosely.
    """
    running = active(store)
    if not running:
        return ""
    if (dev := dev_of(owner)):
        mine = [f for f in facts(store)
                if f["sort"] == "objective" and dev_of(f["owner"]) == dev and f["milestone"]]
        if mine and (found := winner(mine)) is not None:
            return found["milestone"]
    return running[0]["id"]
