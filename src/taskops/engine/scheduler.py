"""Choosing what an agent does next, and claiming it without a race.

Three jobs, in the order they matter:

**Unblock.** `ready` is a stored status, so something has to move a task there when
its last dependency closes. `unblock` is that one writer — nothing else in the
package may set `ready` — which is what keeps the column from drifting away from the
dependency graph.

**Score.** Priority first, then the anti-collision term: a task whose `files`
overlap what a LIVE agent is editing sorts last. Two agents in one file is a merge
conflict that both of them will spend context on, and the cheapest place to prevent
it is here, before either has started.

**Claim.** One INSERT on a primary key, under a transaction that took the write lock
before it read. See `_leases` for why that ordering is the whole story.
"""

from __future__ import annotations

from .._clock import LEASE_TTL, now
from .._ids import slugify
from .._types import OPEN_STATUSES, WORKING_STATUSES, Status
from ..contracts import Lease, Task
from ..storage import Store
from .log import record

__all__ = ["unblock", "ready_tasks", "score", "claim", "branch_for", "sweep_dead"]

_COLLISION_PENALTY = 100
"""Bigger than any priority band, so a file collision always outranks urgency.

Deliberate: an urgent task handed to a second agent in the same file is not urgent
work, it is two agents about to undo each other. The penalty defers it, never
hides it — nothing else is pickable and it comes back to the top.
"""


def sweep_dead(store: Store, *, at: float | None = None) -> list[str]:
    """Expire silent leases and walk their tasks back to `ready`. Returns those ids.

    The crash-recovery path, and it runs at the START of every claim rather than on a
    timer: a daemon would be another process to keep alive, and the moment anyone
    asks for work is exactly when a stuck task matters.
    """
    when = now() if at is None else at
    freed: list[str] = []
    for task_id in store.leases.sweep(when):
        task = store.tasks.get(task_id)
        if task is None or task["status"] not in WORKING_STATUSES:
            continue
        if task["status"] == "review":
            freed.append(task_id)   # a verifier died: still finished, still unverified
            continue
        store.tasks.set_status(task_id, "ready", when=when)
        # RECORDED: a `claimed` replays onto other clones now, so an expiry that stayed
        # local would leave every teammate showing a card held by an agent that died.
        record(store, task=task_id, actor="taskops", kind="status",
               body={"to": "ready", "why": "the lease expired"}, ts=when)
        freed.append(task_id)
    return freed


def unblock(store: Store, *, at: float | None = None) -> list[str]:
    """Promote every `backlog` task whose dependencies are all closed. Returns ids.

    Also demotes: a `ready` task that gained a dependency goes back to `backlog`, so
    a mid-flight discovery cannot leave pickable work that is not actually pickable.
    """
    when = now() if at is None else at
    changed: list[str] = []
    for task in store.tasks.with_status(("backlog", "ready")):
        blocked = bool(store.deps.open_blockers_of(task["id"]))
        target: Status = "backlog" if blocked else "ready"
        if task["status"] != target:
            store.tasks.set_status(task["id"], target, when=when)
            if target == "ready":
                changed.append(task["id"])
    return changed


def ready_tasks(store: Store, *, labels: tuple[str, ...] = (),
                actor: str = "") -> list[Task]:
    """Pickable work for this actor, best first. Call `unblock` before this, or it lies.

    Assignment FILTERS, it does not merely sort: a card assigned to somebody else is not offered at
    all, and the caller's own assigned cards come before the open pool. Without the filter,
    "assigned" would be a label any agent could ignore, and dispatch could not promise a worker that
    the card it was launched for is still there when it asks.
    """
    pool = [t for t in store.tasks.with_status(("ready",))
            if not t["assignee"] or t["assignee"] == actor]
    if labels:
        wanted = set(labels)
        pool = [t for t in pool if wanted & set(t["labels"])]
    busy = _busy_files(store)
    return sorted(pool, key=lambda t: (0 if t["assignee"] == actor and actor else 1,
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


def branch_for(task: Task) -> str:
    """`tk/<id>/<slug>` — the shape the commit guard matches on.

    Composed here rather than left to the agent because the guard's regex and this
    string are one contract, and an agent inventing `feature/tk-4f2a` would be
    denied its own commits with no clue why.
    """
    return f"tk/{task['id']}/{slugify(task['title'])}"


def claim(store: Store, task: Task, *, actor: str, session: str = "",
          at: float | None = None, ttl: float = LEASE_TTL) -> Lease | None:
    """Take the lease, or None if somebody got there first.

    None rather than an exception: losing a race is the NORMAL outcome when twenty
    agents ask for work at once, and the caller's response is to try the next task,
    not to handle an error.
    """
    when = now() if at is None else at
    lease = Lease(task=task["id"], actor=actor, session=session, branch="",
                  acquired=when, expires=when + ttl)
    return lease if store.leases.acquire(lease) else None


def open_children(store: Store, task_id: str) -> int:
    """How many subtasks are still open — the fact the `done` guard needs."""
    return sum(1 for child in store.tasks.children(task_id)
               if child["status"] in OPEN_STATUSES)


def hand_back(store: Store, task_id: str, *, at: float | None = None) -> None:
    """Everything a release lets go of: the lease, and the ASSIGNMENT.

    Back means back to the pool. Leaving the assignee made a released card invisible to
    everyone except the agent that had just said it could not do it — a dead card that read as
    somebody's, and drew the same specialist re-dispatched onto it twice in one day. The
    releaser may still take it again: ready is ready. Lives here, beside `unblock`, because
    what a card lets go of on a transition is scheduler semantics — a transport that decided
    this would be a second opinion waiting to disagree.
    """
    when = now() if at is None else at
    store.leases.release(task_id)
    store.tasks.set_assignee(task_id, "", when=when)
