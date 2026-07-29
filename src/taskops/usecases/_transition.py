"""One status transition, checked and applied — the half of `update` that moves a card.

Split from `update.py` when the release repair would not fit the code budget, and the split is
the honest reading of that refusal: `update` ORCHESTRATES (say, block, move, unblock, reply)
and this MOVES, which is a different concern with its own rules about what a card lets go of.
"""

from __future__ import annotations

from .._clock import now
from .._errors import BadRequest
from .._types import Status
from ..contracts import Task
from ..engine import check_move, hand_back, record
from ..storage import Store
from ._facts import facts_for

__all__ = ["move", "RELEASE"]

RELEASE = "released"
"""Not a status — the WORD an agent uses to hand work back. It maps to `ready` plus dropping
the lease AND the assignment, and it reads as an action because that is what the agent is
doing. Spelling it `ready` in the tool would invite "set ready" as a way of skipping the
queue."""


def move(store: Store, task: Task, who: str, asked: str, comment: str,
          no_code: bool, *, evidence: str = "", no_evidence: str = "") -> Task:
    """Check the move, then apply it. `released` hands the card back — the lease AND the assignment.

    `evidence` and `no_evidence` are carried into the `done` event rather than left in the
    comment, because the whole point of the escape hatch is that a review can FIND the closures
    that skipped it — a reason buried in prose is a reason nobody audits.
    """
    target: Status = "ready" if asked == RELEASE else _status(asked)
    facts = facts_for(store, task, who, no_code=no_code, justification=comment,
                      evidence=evidence, no_evidence=no_evidence)
    check_move(facts, target)
    if asked == RELEASE:
        hand_back(store, task["id"])          # the lease AND the assignment — see the engine
    elif target in ("ready", "done", "cancelled", "review"):
        # `review` releases the LEASE and keeps the assignee. The work is finished and the card
        # is waiting for somebody ELSE, so a held card would say "in hand" about nobody — and
        # a verifier dispatched onto it correctly refuses to touch what another actor holds,
        # which is how a card got verified and left unchanged. Safe by the table above:
        # `review -> done` takes `closing`, not `_needs_lease`, so the reviewer needs no claim;
        # `review -> in_progress` DOES need one, so a worker coming back re-claims; and with no
        # lease left to expire, `sweep_dead` cannot drag it back to `ready`.
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


