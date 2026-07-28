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

from .._clock import now
from .._errors import BadRequest
from .._types import Status
from ..contracts import Task, UpdateResult
from ..engine import check_move, record, unblock
from ..storage import Store
from ._facts import facts_for
from ._project import caller, heartbeat, project
from ._routing import routed, update_remotely, whoami

__all__ = ["update", "RELEASE"]

RELEASE = "released"
"""Not a status — the WORD an agent uses to hand work back. It maps to `ready` plus
dropping the lease, and it reads as an action because that is what the agent is doing.
Spelling it `ready` in the tool would invite an agent to "set ready" as a way of
skipping the queue."""


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
            "comment": comment, "mentions": list(mentions),
            "blocked_on": blocked_on, "no_code": no_code, "evidence": evidence, "no_evidence": no_evidence})
    with project(start) as store:
        who = caller(store, actor)["id"]
        heartbeat(store, who)
        task = store.tasks.need(task_id)
        if comment or mentions:
            _say(store, task_id, who, comment, mentions)
        if blocked_on:
            _block_on(store, task, who, blocked_on)
        if status:
            task = _move(store, task, who, status, comment, no_code,
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
    store.tasks.need(blocker)
    if blocker == task["id"]:
        raise BadRequest(f"{blocker} cannot block itself")
    store.deps.add(blocker, task["id"])
    record(store, task=task["id"], actor=who, kind="blocked", body={"on": blocker})


def _move(store: Store, task: Task, who: str, asked: str, comment: str,
          no_code: bool, *, evidence: str = "", no_evidence: str = "") -> Task:
    """Check the move, then apply it. `released` also drops the lease.

    `evidence` and `no_evidence` are carried into the `done` event rather than left in the
    comment, because the whole point of the escape hatch is that a review can FIND the closures
    that skipped it — a reason buried in prose is a reason nobody audits.
    """
    target: Status = "ready" if asked == RELEASE else _status(asked)
    facts = facts_for(store, task, who, no_code=no_code, justification=comment,
                      evidence=evidence, no_evidence=no_evidence)
    check_move(facts, target)
    if target in ("ready", "done", "cancelled"):
        store.leases.release(task["id"])
    store.tasks.set_status(task["id"], target, when=now())
    record(store, task=task["id"], actor=who,
           kind="done" if target == "done" else "status",
           body={"from": task["status"], "to": target, "released": asked == RELEASE,
                 "unpushed": facts.unpushed, "evidence": evidence,
                 "no_evidence": no_evidence})
    return store.tasks.need(task["id"])


def _status(asked: str) -> Status:
    """A caller's word -> a status the machine knows.

    Validated here rather than trusted from the schema: the CLI and the HTTP surface
    reach this too, and only MCP hosts enforce an enum.
    """
    known = ("backlog", "ready", "claimed", "in_progress", "blocked", "review",
             "done", "cancelled")
    if asked not in known:
        raise BadRequest(f"`{asked}` is not a status — use one of "
                         f"{', '.join(known)}, or `{RELEASE}` to hand the task back")
    return asked            # type: ignore[return-value]


