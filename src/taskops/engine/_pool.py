"""What an agent is OFFERED, and in what order. The other half of `scheduler`.

Split from it when the assignment fold pushed that module past its budget, and the seam is real:
`scheduler` owns the mechanics of a claim — unblock, sweep, lease, branch — while this answers a
question with no writes in it, *which ready cards are this actor's to see, best first*. That is
also why every rule here is testable from three literals and no store.
"""

from __future__ import annotations

from .._clock import now
from ..contracts import Task
from ..storage import Store
from .identity import assigned_to

__all__ = ["ready_tasks", "score"]

_COLLISION_PENALTY = 100
"""Bigger than any priority band, so a file collision always outranks urgency.

Deliberate: an urgent task handed to a second agent in the same file is not urgent
work, it is two agents about to undo each other. The penalty defers it, never
hides it — nothing else is pickable and it comes back to the top.
"""


def ready_tasks(store: Store, *, labels: tuple[str, ...] = (),
                actor: str = "") -> list[Task]:
    """Pickable work for this actor, best first. Call `unblock` before this, or it lies.

    Assignment FILTERS, it does not merely sort: a card assigned to somebody else is not offered at
    all, and the caller's own assigned cards come before the open pool. Without the filter,
    "assigned" would be a label any agent could ignore, and dispatch could not promise a worker that
    the card it was launched for is still there when it asks.

    "Own" is `assigned_to`, so a card dispatched to `dev:ana` is offered to `agent:ana/w1` — and to
    nobody else's agents. Comparing raw ids here hid a person's own work from every worker they
    spawned, which is the pool half of the same bug the by-id claim had.
    """
    pool = [t for t in store.tasks.with_status(("ready",))
            if not t["assignee"] or assigned_to(t["assignee"], actor)]
    if labels:
        wanted = set(labels)
        pool = [t for t in pool if wanted & set(t["labels"])]
    busy = _busy_files(store)
    return sorted(pool, key=lambda t: (0 if assigned_to(t["assignee"], actor) else 1,
                                      score(t, busy), t["created"]))


def _busy_files(store: Store) -> set[str]:
    """Files that a live lease is plausibly editing right now."""
    out: set[str] = set()
    for lease in store.leases.live(now()):
        task = store.tasks.get(lease["task"])
        if task is not None:
            out |= set(task["files"])
    return out


def score(task: Task, busy_files: set[str]) -> int:
    """Lower is better. Priority, plus a penalty for touching occupied files."""
    collides = bool(busy_files & set(task["files"]))
    return task["priority"] + (_COLLISION_PENALTY if collides else 0)
