"""review — claim a submitted card to review it, or record the verdict.

Two moves on one verb, decided by whether `verdict=` is present:

* no verdict → CLAIM the review lease (`store/reviews.py`, one row one winner)
  and get the full dossier back, exactly like a take. The work lease is not
  touched: the worker deliberately stays alive while the verifier reads.
* verdict=pass|changes → append a `reviewed` event and drop the review lease.
  The verdict is an event, never a mutated field, so two racing verdicts can
  never corrupt anything — both land in the thread and a human decides.

The one rule that gives review its entire value: **you may not pass your own
work.** Without it the feature is theatre.
"""

from __future__ import annotations

from typing import Any

from . import _args, _facts, _context
from .. import _clock
from ..core import review
from ..store import reviews
from .._errors import Refused, BadRequest
from ..core.event import make
from ..store.stores import Stores


def run(stores: Stores, actor: str, args: _args.Args) -> dict[str, Any]:
    now = _clock.now()
    card = _facts.find(stores, _args.ident(args, "task"))
    if not card.get("review"):
        raise Refused(
            f"{card['id']} does not require review — its worker closes it: "
            f'taskops_update task={card["id"]} status=done note="…"'
        )
    stood = review.standing(stores.events(card["id"]))
    if not stood.submitted_at:
        raise Refused(
            f"{card['id']} has not been handed in — the worker submits it first: "
            f'taskops_update task={card["id"]} status=review note="<what was done>"'
        )
    if actor == stood.submitted_by:
        raise Refused(
            f"you submitted {card['id']}; somebody else reviews it. "
            "Ask the orchestrator to assign a reviewer."
        )
    verdict = _args.text(args, "verdict", default="")
    if not verdict:
        return _claim(stores, actor, card["id"], now)
    return _judge(stores, actor, card["id"], verdict, args, now)


def _claim(stores: Stores, actor: str, task: str, now: float) -> dict[str, Any]:
    if not reviews.claim(stores.live, task, actor, now):
        holder = reviews.reviewer(stores.live, task, now)
        raise Refused(
            f"{task} is already being reviewed by {holder} — one verifier per card. "
            "Run taskops_board to see what else waits."
        )
    stores.live.renew(actor, now)
    return _context.dossier(stores, actor, _facts.find(stores, task), now)


def _judge(
    stores: Stores, actor: str, task: str, verdict: str, args: _args.Args, now: float
) -> dict[str, Any]:
    if verdict not in review.VERDICTS:
        raise BadRequest(
            f"verdict={verdict!r} — it is 'pass' (ready to close) or 'changes' "
            "(back to the worker, note= says what to change)"
        )
    note = _args.text(args, "note", default="")
    if not note:
        raise Refused(
            'a verdict needs a note: verdict=pass note="what was checked", or '
            'verdict=changes note="what to change" — the worker is shown it verbatim'
        )
    seq = stores.write([make(task, actor, "reviewed", {"verdict": verdict, "note": note}, now)])
    reviews.drop(stores.live, task, actor)
    stores.live.renew(actor, now)
    fresh = _facts.find(stores, task)
    return {
        "card": fresh,
        "verdict": verdict,
        "seq": seq,
        "pulse": _context.pulse(stores, actor, now, fresh["milestone"]),
    }
