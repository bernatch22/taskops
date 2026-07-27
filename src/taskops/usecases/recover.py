"""`taskops recover` — unstick a fleet whose workers died.

Written the day it was needed. Six cards in a real project sat `claimed` by six agents that had been
killed mid-run (an API balance ran out), and getting them back took six hand-written `update
--status released` calls plus a manual hunt through six worktrees for work that had never been
committed. That is the wrong shape for something that will happen every time a fleet dies.

**It does not wait for the lease.** A TTL is the right mechanism for a crash nobody noticed, but a
person looking at a board full of SILENT rows has already noticed — making them wait fifteen minutes
for a timer to agree with them is a tool arguing with its user.

**It never deletes anything.** A dead worker's worktree keeps whatever it wrote, and the recovery
records that in the card's thread instead of tidying it away. Uncommitted work in a directory nobody
mentions is work the next agent redoes from scratch, which was exactly what nearly happened.

**Two kinds of stuck, and the second is easy to miss.** A card can be held by a lease whose worker
went quiet, OR merely ASSIGNED to a worker that was never started — which is what a `dispatch` whose
sub-agents nobody spawned leaves behind. The second has no lease at all, so a recovery that only
swept leases left eight of them assigned to workers that did not exist: invisible to every other
agent, and unclaimable forever. Found by running it.
"""

from __future__ import annotations

from pathlib import Path

from .._clock import HEARTBEAT_GRACE, now
from ..engine import fleet
from ..storage import Store
from ._freeing import Stuck, release_lease, unassign
from ._project import caller, heartbeat, project

__all__ = ["recover", "Recovered", "Stuck"]


class Recovered:
    def __init__(self, *, released: list[Stuck], alive: list[str]) -> None:
        self.released = released
        self.alive = alive
        """Workers still reporting. Named, not silently skipped: a recovery that quietly left two
        cards claimed is a recovery somebody has to check by hand anyway."""


def recover(start: Path | str, *, actor: str = "", grace: float = HEARTBEAT_GRACE,
            force: bool = False) -> Recovered:
    """Release every card whose worker has gone quiet. Returns what was freed and what was not.

    `grace` is the silence a worker is allowed before it counts as gone — the same number the fleet
    view uses to print SILENT, so what you see is what this acts on. `force` releases even the ones
    still reporting, which is for the case where a fleet is alive and wrong.
    """
    with project(start) as store:
        who = caller(store, actor)["id"]
        heartbeat(store, who)
        when = now()
        live = {m["task"]: m for m in fleet(store, at=when)["members"]}
        released: list[Stuck] = []
        alive: list[str] = []
        for lease in store.leases.live(when):
            member = live.get(lease["task"])
            quiet = when - (member["last_seen"] if member else lease["acquired"])
            if not force and quiet < grace:
                alive.append(f"{lease['actor']} on {lease['task']}")
                continue
            released.append(release_lease(store, lease, who, quiet))
        released += _orphans(store, who)
        return Recovered(released=released, alive=alive)


def _orphans(store: Store, who: str) -> list[Stuck]:
    """Cards ASSIGNED to a worker that holds no lease — a dispatch nobody spawned.

    Always recovered, with no grace period, because there is nothing to wait for: an assignment with
    no lease means the worker never started, and the card is meanwhile hidden from every other agent
    by the very filter that makes assignment useful. Left alone it is unclaimable forever.
    """
    out: list[Stuck] = []
    for task in store.tasks.all():
        if not task["assignee"] or store.leases.get(task["id"]) is not None:
            continue
        if task["status"] in ("done", "cancelled"):
            continue
        out.append(unassign(store, task["id"], task["assignee"], who))
    return out
