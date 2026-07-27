"""Gathering what the state machine is allowed to know.

`engine.machine` holds guards that are pure functions of `Facts`, which is what lets every rule be
tested from literals with no database. Something still has to READ those facts, and this is it — the
one place that turns a task plus a store plus git into the record the machine decides on.

Its own module because the reading is not the deciding. `update` orchestrates; the machine judges;
this fetches. When a guard needs a new fact, the change is one function here and one line there.
"""

from __future__ import annotations

from .._clock import now
from ..contracts import Task
from ..engine import Facts, branch_state, open_children
from ..storage import Store

__all__ = ["facts_for", "unpushed_on"]


def facts_for(store: Store, task: Task, actor: str, *, no_code: bool,
              justification: str) -> Facts:
    """Everything the guards may ask about, read once."""
    lease = store.leases.get(task["id"])
    return Facts(
        task=task, actor=actor,
        has_live_lease=store.leases.held_by(task["id"], actor, now()),
        commits=len(store.events.of_task(task["id"], kinds=("commit",))),
        open_children=open_children(store, task["id"]),
        no_code=no_code, justification=justification,
        unpushed=unpushed_on(store, lease["branch"] if lease else ""))


def unpushed_on(store: Store, branch: str) -> int:
    """Commits on this branch that no remote has. 0 when there is no branch or no remote.

    Read at CLOSE time rather than stored: it changes every time anybody pushes, so a cached answer
    would be wrong more often than right.

    A branch with no upstream returns 0 and not "everything", deliberately. Git has nothing to
    compare against there, so any number would be invented — and a solo developer with no remote at
    all would otherwise see every task reported as unpushed forever.
    """
    if not branch:
        return 0
    state = branch_state(store.root, branch)
    if not state["exists"] or not state["upstream"]:
        return 0
    return state["ahead"]
