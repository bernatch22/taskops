"""The state machine, and the ONLY place a status move is decided.

Two tables and no `if status ==` anywhere else in the package — `tests/architecture`
enforces the second half. A transition table plus one convenient status check
somewhere is two state machines, and the convenient one is always the one that
forgot the guard.

Guards are pure functions of `Facts`, not of a database. That is what makes the rules testable
from literals — "a claimed task cannot be closed without a commit" is three lines here, not a
fixture with a repository in it — and it means the use case that ASSEMBLES the facts is the
only thing that needs a store.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .._errors import GuardFailed, IllegalTransition
from .._types import Status
from ..contracts import Task
from ._acceptance import Evidence
from ._review import closing

__all__ = ["Facts", "TRANSITIONS", "check_move", "allowed_from"]


@dataclass(frozen=True, slots=True)
class Facts:
    """Everything the guards are allowed to know. Assembled by `usecases.update`."""

    task: Task
    actor: str
    has_live_lease: bool
    commits: int
    """Commits bound to this task — the evidence `done` demands."""

    open_children: int
    no_code: bool
    """The caller's explicit declaration that this task produces no commit."""

    justification: str
    """The comment accompanying `no_code`. A claim with no reasoning is a bypass."""

    unpushed: int
    """Commits on this branch no remote has. Recorded on close, never blocking — see `_review`."""

    evidence: Evidence | None = None
    """The card's criteria and what the closer offered against them. Defaulted, so every card
    that has none — which is every card written before criteria existed — is unaffected."""

    reviewer: str = ""
    """Who this card names as its reviewer, straight off the row. Defaulted to "", so every
    card created before the field existed is judged by exactly the rules it always was."""

    comment: str = ""
    """The text the caller sent with this move. Read by ONE guard — the rejection — and
    defaulted so no other transition changes shape."""

    entered_review_by: str = ""
    """Who moved this card INTO review, if that was the last status move — read off the event
    log by `usecases._facts`, never stored. Empty for every card that never went through
    review, which is what makes the handoff rule in `_review` cost the old flows nothing."""


Guard = Callable[[Facts], str | None]
"""None means allowed; a string is the reason, written for the agent that is stuck."""


def _needs_lease(facts: Facts) -> str | None:
    if facts.has_live_lease:
        return None
    return (f"{facts.actor} holds no live lease on {facts.task['id']} — claim it "
            f"with taskops_next before working on it")


def _needs_findings(facts: Facts) -> str | None:
    """`review → ready` is the REJECTION, and a rejection with no finding is a card bounced
    with nothing to act on: the worker reads "not good enough", guesses, and the card goes
    round twice for no reason.

    The rule is not new — `tasks reject` has demanded a reason since it existed. It lived in
    ARGPARSE, so it held for a person on a terminal and not for the verifier, which is an agent
    calling `taskops_update status=ready` through MCP. Every rejection an agent ever made
    arrived blank. A rule the state machine does not know is a rule two transports disagree
    about, and the one that skips it is always the one doing the work.
    """
    if facts.comment.strip():
        return None
    return (f"{facts.task['id']} is going back to its worker with no findings — say what "
            f"failed and what shows it (a test name, a command, a run). A rejection with "
            f"nothing to act on sends the card round twice.")


TRANSITIONS: dict[Status, dict[Status, Guard | None]] = {
    "backlog": {"ready": None, "cancelled": None},
    "ready": {"claimed": _needs_lease, "backlog": None, "cancelled": None},
    "claimed": {"review": _needs_lease, "done": closing,
                "ready": None, "blocked": _needs_lease, "cancelled": None},
    "blocked": {"ready": None, "backlog": None, "claimed": _needs_lease,
                "cancelled": None},
    # `ready` is the reviewer's SEND-BACK, and it takes no lease on purpose: the reviewer
    # holds nothing (review released the lease), and demanding one would leave findings with
    # no way to act on them — watched live: a verifier that had proven the work could neither
    # close the card nor return it, and a whole session went to negotiating with the board.
    # The assignee survives the move, so only the worker it belongs to picks it back up.
    # `review → done` takes no lease HERE, and that is deliberate: a person closing a review
    # they just read must not have to claim it first, and every existing flow depends on it.
    # Exclusivity is won a layer up instead — `_transition` takes the lease ON BEHALF of the
    # closer, so a second checker meets a held card rather than duplicating the first.
    "review": {"done": closing, "claimed": _needs_lease, "ready": _needs_findings,
               "blocked": None, "cancelled": None},
    "done": {},
    "cancelled": {"backlog": None},
}
"""Who may go where.

`claimed → done` exists, so `in_progress` is never MANDATORY. Requiring the intermediate step
would add a call to every task's lifecycle for no information the commit does not already
carry — and it is the GUARD, not the path taken to reach it, that protects the board. An agent
that wants its work shown in flight sets `in_progress`; one that claimed, coded, committed and
closed has done nothing wrong. (The missing arrow was found by the end-to-end test, which is
the kind of bureaucracy only a full run reveals.)

`done` is TERMINAL on purpose: reopening would make the log say a task was finished
twice, and the honest record of "we shipped it and it was wrong" is a new task that
references the old one.

`→ ready` from a working status is the RELEASE path, and it is deliberately unguarded: an
agent that is out of context or out of depth must always be able to hand work back, and a
guard there would make the alternative — abandoning it until the lease lapses — the easier
move.
"""


def allowed_from(status: Status) -> tuple[Status, ...]:
    """Where a task in this status can go. Used in the error message, so a
    rejected caller learns the shape of the machine instead of guessing."""
    return tuple(TRANSITIONS.get(status, {}))


def check_move(facts: Facts, new: Status) -> None:
    """Raise unless this move is legal AND earned. Silent on success.

    Two error types, because they are two different conversations: the arrow does not exist
    (nothing to do about it), versus the arrow exists and the work is not there yet (do it).
    """
    old: Status = facts.task["status"]
    outgoing = TRANSITIONS.get(old, {})
    if new not in outgoing:
        raise IllegalTransition.between(task=facts.task["id"], old=old, new=new,
                                        allowed=allowed_from(old))
    guard = outgoing[new]
    refusal = guard(facts) if guard else None
    if refusal:
        raise GuardFailed(refusal)
