"""The milestone state machine — the ONLY place a chapter's move is decided.

Same shape as `machine.py` and for the same reasons: one table of legal arrows, guards that are
pure functions of what was attempted, and a refusal that names the way out. A chapter moves like
a card because it IS the same argument one level up — whoever did the work does not get to say it
is done — so the verbs are the card's verbs (`start`, `review`, `done`, `reject`, `cancel`).

Nothing here reads a store, a clock or an environment: a state, an actor and the message that
came with the move go in, and a refusal or `None` comes out. That is what makes "an agent may not
close its own chapter" a three-line test from literals instead of a fixture with a board in it.

**There is deliberately NO uniqueness guard.** Several milestones sit in `OPEN_MILESTONE` at once
on any real board, and a rule that allowed one would force a chapter somebody is demonstrably
working on to read `planned`. The slice bound is the CARD — a card belongs to exactly one
milestone — so nothing here has any business counting the board. See `contracts.milestone`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..contracts.milestone import MilestoneState
from . import identity
from ._chapters import illegal, needs_a_person, needs_findings

__all__ = ["Attempt", "MOVES", "allowed_from", "move"]


@dataclass(frozen=True, slots=True)
class Attempt:
    """Everything the guards are allowed to know about a move."""

    milestone: str
    """Its id — quoted back in every refusal, because the way out is a command that needs it."""

    state: MilestoneState
    actor: str
    note: str = ""
    """The message that came with the move: the review report, the reject reason, the cancel
    reason. Read by ONE guard — the rejection — and defaulted, so no other arrow changes shape."""


Guard = Callable[[Attempt], str | None]
"""None means allowed; a string is the reason, written for the caller that is stuck."""


def _a_person(verb: str) -> Guard:
    """`done`, `reject` and `cancel` are a person's, and this is `done`-on-a-card one level up.

    An agent that could verify the chapter it reported would be grading itself with the board's
    own vocabulary, and then no count of closed cards could mean "we shipped it" — which is the
    single question the record exists to answer. The refusal names the report instead of saying
    no: this repo has paid four debugging sessions for refusals that only said no.
    """
    def guard(attempt: Attempt) -> str | None:
        if identity.parse(attempt.actor)["kind"] != "agent":
            return None
        return needs_a_person(attempt.actor, verb, attempt.milestone)
    return guard


def _rejection(attempt: Attempt) -> str | None:
    """A chapter sent back with no findings leaves whoever reported it with nothing to do.

    Same rule as a card's rejection and the same reason it lives HERE: in argparse it would hold
    for a person at a terminal and not for the verifier arriving through MCP.
    """
    return _a_person("reject")(attempt) or (
        None if attempt.note.strip() else needs_findings(attempt.milestone))


MOVES: dict[MilestoneState, dict[MilestoneState, Guard | None]] = {
    "planned": {"in_force": None, "abandoned": _a_person("cancel")},
    # `done` straight from `in_force` is deliberate: a person who read the work may verify a
    # chapter no agent ever reported, and demanding the intermediate `review` would add a call
    # that carries no information the verification does not already have.
    "in_force": {"review": None, "reached": _a_person("done"),
                 "abandoned": _a_person("cancel")},
    "review": {"reached": _a_person("done"), "in_force": _rejection,
               "abandoned": _a_person("cancel")},
    "reached": {},
    "abandoned": {},
}
"""Who may go where.

`start` and `review` carry no guard: planning is an agent's job and so is reporting, and a
chapter nobody may move out of `planned` is a todo-list with a lock on it.

`reached` and `abandoned` are TERMINAL, both of them. Reopening would make the log say a chapter
was finished twice, and "we stopped" is kept apart from "we shipped" precisely so that neither
can be edited into the other later — the whole reason abandoning is a state and not a delete.
"""


def allowed_from(state: MilestoneState) -> tuple[MilestoneState, ...]:
    """Where a chapter in this state can go. Quoted in the refusal, so a stuck caller learns
    the shape of the machine instead of guessing at the next arrow."""
    return tuple(MOVES.get(state, {}))


def move(state: MilestoneState, to: MilestoneState, actor: str,
         note: str = "", milestone: str = "") -> str | None:
    """The refusal for this move, or None if it is legal AND earned.

    Returns rather than raises: the caller is a use case that owns the error vocabulary, and
    every refusal in here is a sentence for a human or an agent to read, not a control-flow
    signal to catch. Two refusals, two conversations — the arrow does not exist (nothing to do
    about it) versus the arrow exists and this actor is not the one who may take it.
    """
    outgoing = MOVES.get(state, {})
    if to not in outgoing:
        return illegal(milestone, state, to, allowed_from(state))
    guard = outgoing[to]
    return guard(Attempt(milestone=milestone, state=state, actor=actor, note=note)) if guard \
        else None
