"""`taskops_update` — a transition, a comment and a notification, in one call.

One call because they are one event in the agent's head: "I finished this, here is what
happened, tell Ana's agent". Three calls would mean three chances to do two of the
three, and the missing one is always the comment.

This is the only place that assembles `Facts` for the state machine. Everything the
guards ask about — a live lease, the commits bound to the task, its open children — is
read here and handed over as data, which is what lets those rules be tested from
literals.
"""

from __future__ import annotations

from pathlib import Path

from .._errors import BadRequest
from ..contracts import Task, UpdateResult
from ..engine import record, unblock
from ..storage import Store
from ._project import caller, heartbeat, project
from ._routing import routed, update_remotely, whoami
from ._transition import move

__all__ = ["update"]



def update(start: Path | str, task_id: str, *, actor: str = "", status: str = "",
           comment: str = "", mentions: tuple[str, ...] = (), blocked_on: str = "",
           no_code: bool = False, evidence: str = "", no_evidence: str = "",
           local: bool = False) -> UpdateResult:
    """Apply whatever was asked, in the order that keeps the graph honest.

    `local` is the server's flag, exactly as in `next_task`: a project with a remote runs
    its transitions THERE, so the lease guard that refuses a `done` from a machine that
    never held the lease is checked against the one database everybody writes to.
    """
    if not (status or comment or blocked_on):
        raise BadRequest("nothing to do — pass a `status`, a `comment`, or `blocked_on`")
    if (remote := routed(start, local)) is not None:
        return update_remotely(start, remote, {
            "task": task_id, "actor": whoami(start, actor), "status": status,
            "comment": comment, "mentions": list(mentions), "blocked_on": blocked_on,
            "no_code": no_code, "evidence": evidence, "no_evidence": no_evidence})
    with project(start) as store:
        who = caller(store, actor)["id"]
        heartbeat(store, who)
        task = store.tasks.need(task_id)
        if comment or mentions:
            _say(store, task_id, who, comment, mentions)
        if blocked_on:
            _block_on(store, task, who, blocked_on)
        if status:
            task = move(store, task, who, status, comment, no_code,
                         evidence=evidence, no_evidence=no_evidence)
        freed = unblock(store)
        return UpdateResult(task=store.tasks.need(task_id),
                            unblocked=[store.tasks.need(i) for i in freed],
                            notified=list(mentions))


def _say(store: Store, task_id: str, who: str, text: str, mentions: tuple[str, ...]) -> None:
    """Record the comment. Mentions make it a `message`, which is what an inbox reads.

    The kind carries the routing rather than a separate flag: `delivered.pending`
    selects on kind and body, so a comment nobody was addressed in cannot end up in
    anybody's inbox by accident.
    """
    record(store, task=task_id, actor=who,
           kind="message" if mentions else "comment",
           body={"text": text, "mentions": list(mentions)})


def _block_on(store: Store, task: Task, who: str, blocker: str) -> None:
    """Add the edge a discovery revealed, and say so in the log.

    The edge is added even when the task is not moved to `blocked`: the graph is the
    thing other agents schedule against, and a dependency that lived only in a comment
    is a dependency the scheduler will hand somebody straight into.
    """
    if blocker == task["id"]:
        raise BadRequest(f"{blocker} cannot block itself")
    store.tasks.need(blocker)
    store.deps.add(blocker, task["id"])
    record(store, task=task["id"], actor=who, kind="blocked", body={"on": blocker})



