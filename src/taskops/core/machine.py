"""The state machine, as pure functions over facts.

**Three** stored statuses — open, done, dropped. `ready`, `blocked`, `stalled`
and `doing` are derived in `graph.py` and are never written. Closing a blocker
frees its dependents by definition; a worker that dies stops renewing its lease
and its card leaves `doing` by itself. Neither needs a writer, so neither can
have a race, a sweep, or a repair verb.

The lease is the mutex; these functions only decide what to SAY. Every refusal
names the call that fixes it — an agent that reads "refused" and cannot see the
way out will invent one.
"""

from __future__ import annotations

from typing import NamedTuple

from . import review
from .types import CLOSED, ROLE_DEV, CARD_STATUSES, Card, role_of
from .._errors import Refused, BadRequest


class Facts(NamedTuple):
    """Everything the guards may look at. Gathering them is the caller's job."""

    status: str  # stored: open | done | dropped
    assignee: str  # who it is FOR, "" for the pool
    holder: str | None  # who holds a LIVE lease right now
    commits: int  # `commit` events bound to this card
    standing: review.Standing = review.EMPTY  # where it stands with its reviewer


def check_take(card: Card, facts: Facts, actor: str) -> None:
    """May `actor` claim this card? The lease decides; this is the message."""
    if facts.status in CLOSED:
        raise Refused(
            f"{card['id']} is {facts.status} — reopen it with "
            f'taskops_update task={card["id"]} status=open note="<why>"'
        )
    if facts.holder is not None and facts.holder != actor:
        raise Refused(
            f"{card['id']} is held by {facts.holder} right now — your card is elsewhere; "
            "run taskops_board to see what is assigned to you"
        )
    if facts.assignee and facts.assignee != actor:
        # No live holder but somebody else's name on it: the worker it was given
        # to went quiet. Reassigning is a decision, and it is the orchestrator's.
        gone = " (its worker went quiet)" if facts.holder is None else ""
        raise Refused(
            f"{card['id']} is assigned to {facts.assignee}{gone} — ask the orchestrator to "
            f"hand it over: taskops_assign tasks=[{card['id']}]"
        )


def check_transition(
    card: Card,
    facts: Facts,
    actor: str,
    to: str,
    *,
    reason: str = "",
    no_code: bool = False,
    has_comment: bool = False,
) -> None:
    """Guard a status write. `to` is one of the three stored statuses."""
    if to not in CARD_STATUSES:
        raise BadRequest(
            f"status {to!r} — the stored ones are {', '.join(CARD_STATUSES)}. "
            "'doing' is not written: it means somebody holds the lease (taskops_take)."
        )
    if facts.status == to:
        raise Refused(f"{card['id']} is already {to}")
    if facts.status == "done" and to != "open":
        raise Refused(f"{card['id']} is done — only 'open' reopens it")
    if to == "done":
        _check_done(card, facts, actor, no_code=no_code, has_comment=has_comment)
    if to == "dropped" and not reason:
        raise Refused(
            f"dropping {card['id']} needs a reason: taskops_update task={card['id']} "
            'status=dropped comment="<why it will never be done>"'
        )


def _check_done(card: Card, facts: Facts, actor: str, *, no_code: bool, has_comment: bool) -> None:
    _not_somebody_elses(card, facts, actor)
    if facts.commits == 0 and not no_code:
        raise Refused(
            f"{card['id']} has no commit bound to it. Commit in your worktree (the "
            "Task: trailer is stamped for you), or close it honestly with "
            f'taskops_update task={card["id"]} status=done no_code=true note="<what happened>"'
        )
    if no_code and not has_comment:
        raise Refused("no_code=true needs a comment saying what happened instead")
    if card.get("review") and facts.standing.verdict != "pass":
        raise Refused(
            f"{card['id']} needs a passing review before it closes. "
            f'Hand it in instead: taskops_update task={card["id"]} status=review note="<what you did>" '
            "— the orchestrator assigns a reviewer and closes it when it passes."
        )


def check_release(card: Card, facts: Facts, actor: str, note: str) -> None:
    """Handing work back is always allowed — but never in silence."""
    if facts.status in CLOSED:
        raise Refused(f"{card['id']} is {facts.status}; there is nothing to hand back")
    _not_somebody_elses(card, facts, actor)
    if not note:
        raise Refused(
            'releasing needs a note: comment="got as far as X, Y is left" — the next '
            "worker is shown it verbatim when they take the card"
        )


def _not_somebody_elses(card: Card, facts: Facts, actor: str) -> None:
    """A lease that lapsed does NOT cost you your own card.

    Only a live holder who is somebody else stops you: if nobody took it in the
    meantime, the worker that did the work still closes it. Demanding a live
    lease would mean a worker who spent twenty quiet minutes editing came back
    to find it could not close what it had just built.
    """
    # The orchestrator closes what a reviewer passed — even while the worker's
    # lease is still live, because in the review flow the worker deliberately
    # stays reachable after handing in. It is not taking the card: it records a
    # decision already made, by somebody who is not the author (the reviewer
    # may never be the submitter). Any wider and `dev:` closes work it never saw.
    if role_of(actor) == ROLE_DEV and card.get("review") and facts.standing.verdict == "pass":
        return
    if facts.holder is not None and facts.holder != actor:
        raise Refused(
            f"{card['id']} is held by {facts.holder} now, not you ({actor}) — "
            "they took it over while you were away"
        )
    if facts.assignee and facts.assignee != actor:
        raise Refused(f"{card['id']} belongs to {facts.assignee}, not you ({actor})")
