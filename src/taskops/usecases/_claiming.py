"""What a claim is ALLOWED to take, and where it leaves the card.

Split from `claim` when the review lease pushed that module past its budget, and the seam is
real: `claim` runs the transaction (sweep, unblock, walk the pool, take the lease), these two
answer the questions it asks about one candidate. Both are pure reads.
"""

from __future__ import annotations

from .._errors import BadRequest
from .._types import Status
from ..contracts import Task
from ..engine.identity import parse
from ..engine.routereview import routed_to
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
    if task["status"] == "review":
        return _review_claimable(task, who)
    return task["status"] == "ready" and task["assignee"] in ("", who)


def _review_claimable(task: Task, who: str) -> bool:
    """Who may claim a review, and the answer depends on WHAT KIND of id holds it.

    An `agent:` assignee is that agent's card — a worker sent back with findings, coming
    home. Anybody else taking it is theft of work in its most fragile state, so the match is
    exact.

    A `dev:` assignee is a ROUTED review: the server chose a reviewer, and a developer reviews
    through their agents. `agent:dos/v1` arriving at a card routed to `dev:dos` is the very
    verifier it was routed to, so the match is by dev. Conflating the two either refused that
    verifier or opened a bounced card to strangers.

    Routing EXPIRES; a stale one opens the card to everybody, exactly as the sweep does.
    """
    from ..engine.routereview import route_is_fresh

    owner = task["assignee"]
    if owner in ("", who):
        return True
    if not owner.startswith("dev:"):
        return False                      # an agent's bounced card is that agent's
    return not route_is_fresh(task) or _same_dev(owner, who)


def _same_dev(owner: str, who: str) -> bool:
    try:
        return parse(owner)["dev"] == parse(who)["dev"]
    except BadRequest:
        return False


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
    # `assignee` answers this ONLY when it is a dispatch. Routing writes the REVIEWER there,
    # so `assignee == who` started reading "the chosen reviewer" as "the worker coming back":
    # the card left `review` on the reviewer's own claim, and every closing rule written
    # against a card in review — the handoff guard, the routing guard — stopped applying to
    # the one close they exist for. Watched on a live board, four cards closed from `claimed`.
    returning = entered_review_by(store, task["id"]) == who or (
        task["assignee"] == who and not routed_to(task))
    return "claimed" if returning else "review"
