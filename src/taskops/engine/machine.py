"""The state machine, and the ONLY place a status move is decided.

Two tables and no `if status ==` anywhere else in the package — `tests/architecture`
enforces the second half. A transition table plus one convenient status check
somewhere is two state machines, and the convenient one is always the one that
forgot the guard.

Guards are pure functions of `Facts`, not of a database. That is what makes the
rules testable from literals — "a claimed task cannot be closed without a commit"
is three lines here, not a fixture with a repository in it — and it means the use
case that ASSEMBLES the facts is the only thing that needs a store.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .._errors import GuardFailed, IllegalTransition
from .._types import Status
from ..contracts import Task

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


Guard = Callable[[Facts], str | None]
"""None means allowed; a string is the reason, written for the agent that is stuck."""


def _needs_lease(facts: Facts) -> str | None:
    if facts.has_live_lease:
        return None
    return (f"{facts.actor} holds no live lease on {facts.task['id']} — claim it "
            f"with taskops_next before working on it")


def _needs_evidence(facts: Facts) -> str | None:
    """`done` requires a commit, or an argued exemption.

    THE guard that makes the board trustworthy. Without it "done" means "an agent
    said so", which is exactly the failure a human is trying to avoid by reading a
    board instead of the diff. The exemption exists because research and decisions
    are real work — but it has to be declared and reasoned, so that a review can
    see which closures had no code and why.
    """
    if facts.commits > 0:
        return None
    if facts.no_code and facts.justification.strip():
        return None
    if facts.no_code:
        return ("no_code needs a `comment` saying what was produced instead — "
                "an unexplained exemption is indistinguishable from a shortcut")
    return (f"{facts.task['id']} has no commit bound to it. Commit your work (the "
            f"guard adds the trailer), or pass no_code with a comment if this task "
            f"legitimately produced none")


def _needs_children_closed(facts: Facts) -> str | None:
    if facts.open_children == 0:
        return None
    return (f"{facts.task['id']} still has {facts.open_children} open subtask(s) — "
            f"an epic is done when its children are")


def _closing(facts: Facts) -> str | None:
    """Both closing rules, in the order a caller can act on them.

    Children first: being told to write a commit for an epic whose subtasks are
    unfinished sends the agent to do the wrong work.
    """
    return _needs_children_closed(facts) or _needs_evidence(facts)


TRANSITIONS: dict[Status, dict[Status, Guard | None]] = {
    "backlog": {"ready": None, "cancelled": None},
    "ready": {"claimed": _needs_lease, "backlog": None, "cancelled": None},
    "claimed": {"in_progress": _needs_lease, "review": _needs_lease, "done": _closing,
                "ready": None, "blocked": _needs_lease, "cancelled": None},
    "in_progress": {"review": _needs_lease, "done": _closing, "blocked": _needs_lease,
                    "ready": None, "cancelled": None},
    "blocked": {"ready": None, "backlog": None, "in_progress": _needs_lease,
                "cancelled": None},
    "review": {"done": _closing, "in_progress": _needs_lease, "blocked": None,
               "cancelled": None},
    "done": {},
    "cancelled": {"backlog": None},
}
"""Who may go where.

`claimed → done` exists, so `in_progress` is never MANDATORY. Requiring the
intermediate step would add a call to the lifecycle of every task in the project in
exchange for no information the commit does not already carry — and it is the GUARD,
not the path taken to reach it, that protects the board. An agent that wants its work
shown in flight sets `in_progress`; one that claimed, coded, committed and closed has
done nothing wrong. (The missing arrow was found by the end-to-end test, which is the
kind of bureaucracy only a full run reveals.)

`done` is TERMINAL on purpose: reopening would make the log say a task was finished
twice, and the honest record of "we shipped it and it was wrong" is a new task that
references the old one.

`→ ready` from a working status is the RELEASE path, and it is deliberately
unguarded: an agent that is out of context or out of depth must always be able to
hand work back, and a guard there would make the alternative — abandoning it until
the lease lapses — the easier move.
"""


def allowed_from(status: Status) -> tuple[Status, ...]:
    """Where a task in this status can go. Used in the error message, so a
    rejected caller learns the shape of the machine instead of guessing."""
    return tuple(TRANSITIONS.get(status, {}))


def check_move(facts: Facts, new: Status) -> None:
    """Raise unless this move is legal AND earned. Silent on success.

    Two error types, because they are two different conversations: the arrow does
    not exist (nothing to do about it), versus the arrow exists and the work is not
    there yet (do the work).
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
