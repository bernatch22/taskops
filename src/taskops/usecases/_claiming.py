"""What a claim is ALLOWED to take, and where it leaves the card.

Split from `claim` when the review lease pushed that module past its budget, and the seam is
real: `claim` runs the transaction (sweep, unblock, walk the pool, take the lease), these two
answer the questions it asks about one candidate. Both are pure reads.
"""

from __future__ import annotations

from .._types import Status
from ..contracts import Task
from ..storage import Store
from ._facts import entered_review_by

__all__ = ["claimable", "lands_on"]


def claimable(task: Task, who: str) -> bool:
    """Ready — or in review — and either unassigned or assigned to this caller.

    `review` is claimable BY ID because of what claiming it means, and it now means two
    things: the worker coming back to fix (the bounce, which needs a lease to move on) and a
    verifier saying "I am checking this". Before either, a bounced-back card was unreachable —
    review had released the lease and the claim refused review outright, so the one agent sent
    back to fix it was told the card was "held by someone else" about a card nobody held.

    Pool calls never see review cards (`ready_tasks` is ready only), so nothing wanders into
    one by asking for "anything": a verification is always deliberate, by id.
    """
    return task["status"] in ("ready", "review") and task["assignee"] in ("", who)


def lands_on(store: Store, task: Task, who: str) -> Status:
    """Where a claim leaves the card — and the only interesting case is `review`.

    Two people arrive at a review card meaning two different things. Its own WORKER coming
    back is leaving the handoff: findings are in, the card is theirs again, `claimed`. Anyone
    else is a VERIFIER saying "I am checking this", and the card must STAY in review for the
    verdict to land — the close guard is written against a card that is in one.

    The lease it takes is what ended triple verification. One real card was checked three
    times in parallel, each run building its own venv, because a review card with no lease
    showed up in every session's sweep at once and nothing said somebody was already on it.
    """
    if task["status"] != "review":
        return "claimed"
    returning = task["assignee"] == who or entered_review_by(store, task["id"]) == who
    return "claimed" if returning else "review"
