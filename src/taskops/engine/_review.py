"""What `→ done` demands: the closing rules, including who is allowed to close.

Extracted from `machine` rather than added to it, and the reason is the file budget only in
part. The machine owns the TABLE — which arrow exists — and these are the questions asked
ONCE an arrow is legal: are the children finished, is there code, is there evidence, and now
the newest one, is the closer somebody other than the agent that asked for the review.

That last rule is the whole point of `review` as a status. A worker that moves its own card to
`review` and then to `done` has invented a review it performed on itself, which is exactly the
signature this board exists to make impossible — "done" would once again mean "an agent said
so". So the arrow stays legal and the CLOSER changes.

Two deliberate holes, both compatibility rather than kindness:

- A `dev:` actor may always close. A human reading the diff IS the review, and a rule that made
  a person hand their own card to an agent would be uninstalled within the hour.
- A card that never passed through `review` closes exactly as it always did. The refusal fires
  only when the log says the last status move was INTO review and names the same actor, so
  every existing flow — claim, commit, done — is untouched.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._types import HUMAN
from ._acceptance import evidenced

if TYPE_CHECKING:                          # pragma: no cover - typing only
    from .machine import Facts

__all__ = ["closing"]


def _reviewer_is_a_person(facts: Facts) -> str | None:
    """A card whose reviewer is a HUMAN refuses `done` from every agent, not just from the one
    that asked for the review.

    This is the half that makes the field policy rather than a note. `_handed_on` below asks a
    weaker question — did you review your own work — and a second agent closing a card a person
    was meant to read passes it while defeating the point of naming that person.

    The refusal NAMES who is expected, because the useful sentence is not "no" but "this one is
    Ana's"; an agent told only that it may not close will try the next thing instead of leaving
    the card in review and saying so.
    """
    who = facts.reviewer
    if who != HUMAN and not who.startswith("dev:"):
        return None
    if not facts.actor.startswith("agent:"):
        return None
    return (f"{facts.task['id']} names {who} as its reviewer — a person closes this one. "
            f"Leave it in `review` and say what you did in a comment; no agent may close it.")


def _handed_on(facts: Facts) -> str | None:
    """Refuse a `done` signed by the same agent that asked for the review.

    `entered_review_by` is derived from the card's EVENTS and not from a column, which is why
    this needs no new state: the log already says who moved it and where to, and a column
    would be a second copy of that answer able to disagree with it.

    Only while the card IS in review. The rule is "you may not close a review you opened", not
    "you may never close a card you once handed over": a verifier sends work back, the worker
    RE-CLAIMS it, and the card is `claimed` again — its own, with no review pending. Refusing
    there stranded the returning worker with nowhere to go, which is exactly what the bounce
    exists to avoid.
    """
    if facts.task["status"] != "review":
        return None
    if not facts.entered_review_by or facts.actor != facts.entered_review_by:
        return None
    if not facts.actor.startswith("agent:"):
        return None
    return (f"{facts.task['id']} is in review because you put it there — review is "
            f"another's to close. Hand it to the verifier (spawn a `taskops-verifier` "
            f"on this card) or have a dev close it.")


def _needs_children_closed(facts: Facts) -> str | None:
    if facts.open_children == 0:
        return None
    return (f"{facts.task['id']} still has {facts.open_children} open subtask(s) — "
            f"an epic is done when its children are")


def _needs_code(facts: Facts) -> str | None:
    """`done` requires a commit, or an argued exemption.

    THE guard that makes the board trustworthy. Without it "done" means "an agent said so",
    which is exactly the failure a human is trying to avoid by reading a board instead of the
    diff. The exemption exists because research and decisions are real work — but it has to be
    declared and reasoned, so a review can see which closures had no code and why.
    """
    if facts.commits > 0 or (facts.no_code and facts.justification.strip()):
        return None
    if facts.no_code:
        return ("no_code needs a `comment` saying what was produced instead — "
                "an unexplained exemption is indistinguishable from a shortcut")
    # "on the task's branch" and not "the guard adds the trailer": the trailer is only injected
    # inside Claude Code, where a hook can rewrite the command. From a terminal the BRANCH is what
    # binds the commit, so naming the branch is the advice that is true in both places.
    return (f"{facts.task['id']} has no commit bound to it. Commit your work on the "
            f"task's branch, or pass no_code with a comment if this task legitimately "
            f"produced none")


def closing(facts: Facts) -> str | None:
    """The closing rules, in the order a caller can act on them: who, then children, then code,
    then the evidence for the card's acceptance criteria (a no-op for a card with none).

    WHO first: telling an agent to write a commit for a card it is not allowed to close sends
    it to do work that will be refused anyway. Children before code for the same reason — an
    epic whose subtasks are unfinished does not need a commit, it needs the subtasks.

    `unpushed` is deliberately NOT a rule here. It is recorded on the `done` event and shown on
    the board instead, because pushing is not always the closer's job — a task can finish on a
    branch somebody else lands — and a repository with no remote would otherwise be unable to
    close anything, which is the most common way taskops is first tried.
    """
    return (_reviewer_is_a_person(facts) or _needs_a_reviewer(facts) or _handed_on(facts)
            or _needs_children_closed(facts) or _needs_code(facts)
            or evidenced(facts.evidence))


def _needs_a_reviewer(facts: Facts) -> str | None:
    """An agent may not close a card that promised checkable things without handing it over.

    A card carrying acceptance criteria is EXACTLY the card somebody else should check — that
    is what criteria are for, and a worker signing off on its own is the self-certification
    the whole review loop exists to prevent. Watched happen: a card with three EARS criteria
    went straight from claimed to done, by the agent that wrote it, minutes after review was
    made optional.

    Optional was the right call for the card it was meant for — a text fix, a rename, work that
    promised nothing to check — and that card has no criteria, so this is a no-op for it. What
    was wrong was letting "optional" mean optional for cards that DID promise something.

    A `dev:` is never stopped: a human reading the diff IS the review.
    """
    if not facts.evidence or not facts.evidence.criteria:
        return None
    if not facts.actor.startswith("agent:") or facts.task["status"] == "review":
        return None
    return (f"{facts.task['id']} carries {len(facts.evidence.criteria)} acceptance criteria — "
            f"somebody else checks those. Hand it over with `status=review` saying which you "
            f"met and how; a verifier (or a dev) closes it from there.")
