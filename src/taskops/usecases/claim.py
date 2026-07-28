"""`taskops_next` — the call an agent makes to start working.

The loop matters: `ready_tasks` is ORDERED, and losing a race on the best task means
trying the next one rather than failing. With twenty agents asking at once, contention
is the normal case, and an implementation that returned an error on a lost race would
have every agent retrying the same task in lockstep.

What comes back is not an id. It is the task, its spec, its conversation, its
collisions, the branch to create and the agent's inbox — everything the next few
minutes need, assembled in the one call the agent was already making.
"""

from __future__ import annotations

from pathlib import Path

from .._clock import now
from ..contracts import Claim, NextResult, Task
from ..engine import branch_for, counts, ready_tasks, record, unblock
from ..engine import claim as take_lease
from ..storage import Store
from ._project import caller, heartbeat, project
from ._reasons import why_nothing
from ._routing import claim_remotely, routed, whoami
from .view import inbox_for, view

__all__ = ["next_task"]


def next_task(start: Path | str, *, actor: str = "", session: str = "",
              labels: tuple[str, ...] = (), task: str = "",
              local: bool = False) -> NextResult:
    """Claim the best available task, or explain why there is none.

    `local` forces the claim into THIS sqlite. It exists for the server, which runs this
    function to answer `POST /api/next` and would otherwise call itself if the store it
    serves happened to carry a `remote.json` — see `_routing`.
    """
    if (remote := routed(start, local)) is not None:
        return claim_remotely(start, remote, {"actor": whoami(start, actor),
                                              "session": session,
                                              "labels": list(labels), "task": task})
    with project(start) as store:
        who = caller(store, actor)["id"]
        # BEFORE any write. Two reasons, and the first one is a bug this ordering fixed:
        # sqlite3 auto-opens a transaction on the first write, and `BEGIN IMMEDIATE` inside
        # one raises. The second is why it belongs first anyway — the sweep, the unblock and
        # the claim are one decision, so they must be one transaction. An unblock that
        # committed separately would publish a ready task this call is about to claim.
        store.claiming()
        heartbeat(store, who)
        unblock(store)
        claimed = _take(store, who, session, labels, task)
        if claimed is None:
            return _result(store, None, why_nothing(store, labels, task, who))
        return _result(store, claimed, "")


def _take(store: Store, who: str, session: str, labels: tuple[str, ...],
          wanted: str) -> Claim | None:
    """Walk the ordered pool until a claim lands. None if every candidate was taken.

    A task asked for BY ID must still be `ready` AND not assigned to somebody else. Both checks were
    missing and both were found by RUNNING the thing, not by review:

    - the dependency check, by following the usage guide: `next --task <id>` on a task whose
      dependency was open handed it over, so the path where a human names the task was the one that
      skipped the graph.
    - the assignment check, by watching a dispatched fleet: a worker invented its own actor id and
      claimed a card assigned to another worker. Filtering `ready_tasks` was not enough, because
      asking by id never went through it.
    """
    if wanted:
        asked_for = store.tasks.need(wanted)
        pool = [asked_for] if _claimable(asked_for, who) else []
    else:
        pool = ready_tasks(store, labels=labels, actor=who)
    for candidate in pool:
        lease = take_lease(store, candidate, actor=who, session=session)
        if lease is None:
            continue
        store.tasks.set_status(candidate["id"], "claimed", when=now())
        record(store, task=candidate["id"], actor=who, kind="claimed",
               body={"session": session, "branch": branch_for(candidate)})
        return Claim(view=view(store, candidate["id"]), lease=lease,
                     branch=branch_for(candidate),
                     inbox=inbox_for(store, who))
    return None


def _claimable(task: Task, who: str) -> bool:
    """Ready, and either unassigned or assigned to this caller."""
    return task["status"] == "ready" and task["assignee"] in ("", who)


def _result(store: Store, claim: Claim | None, reason: str) -> NextResult:
    """The answer, always carrying the queue's shape.

    The counts ride along on SUCCESS too, not only on failure: an agent that just took
    the last ready task and can see that knows to plan rather than come straight back.
    """
    numbers = counts(store)
    return NextResult(claim=claim, reason=reason, ready=numbers["ready"],
                      working=numbers["working"], blocked=numbers["blocked"])
