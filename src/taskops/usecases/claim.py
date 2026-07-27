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
from ..contracts import Claim, NextResult
from ..engine import branch_for, counts, ready_tasks, record, unblock
from ..engine import claim as take_lease
from ..storage import Store
from ._project import caller, heartbeat, project
from .view import inbox_for, view

__all__ = ["next_task"]


def next_task(start: Path | str, *, actor: str = "", session: str = "",
              labels: tuple[str, ...] = (), task: str = "") -> NextResult:
    """Claim the best available task, or explain why there is none."""
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
            return _result(store, None, _reason(store, labels, task))
        return _result(store, claimed, "")


def _take(store: Store, who: str, session: str, labels: tuple[str, ...],
          wanted: str) -> Claim | None:
    """Walk the ordered pool until a claim lands. None if every candidate was taken."""
    pool = [store.tasks.need(wanted)] if wanted else ready_tasks(store, labels=labels)
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


def _result(store: Store, claim: Claim | None, reason: str) -> NextResult:
    """The answer, always carrying the queue's shape.

    The counts ride along on SUCCESS too, not only on failure: an agent that just took
    the last ready task and can see that knows to plan rather than come straight back.
    """
    numbers = counts(store)
    return NextResult(claim=claim, reason=reason, ready=numbers["ready"],
                      working=numbers["working"], blocked=numbers["blocked"])


def _reason(store: Store, labels: tuple[str, ...], wanted: str) -> str:
    """Why there is nothing to do. "Nothing ready" alone sends the agent to ask a
    human; told WHICH — all blocked, all taken, or genuinely finished — it can act."""
    if wanted:
        return f"{wanted} is claimed by someone else — read it with taskops_ask"
    numbers = counts(store)
    if numbers["open"] == 0:
        return "nothing open — the project is finished, or nothing has been planned"
    if labels:
        return (f"no ready task carries {', '.join(labels)}. Drop the label filter, "
                f"or plan the work that is missing")
    if numbers["ready"] == 0 and numbers["blocked"]:
        return (f"{numbers['blocked']} task(s) are waiting on a dependency and "
                f"{numbers['working']} are in flight — unblocking one of those is "
                f"the useful move")
    return (f"every ready task was claimed by another agent in the last moment "
            f"({numbers['working']} in flight) — ask again")
