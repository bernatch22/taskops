"""take — a worker claims a card and gets the whole world back. Agents only.

Three things happen in one call, and the order is deliberate:

1. **The lease is acquired first** (`INSERT OR IGNORE`, one row, one winner).
   Only then is the `claimed` event written, so a lost race never leaves a
   claim in the log.
2. `title=` creates AND claims in the same transaction — v1 had this as
   plan-then-claim and it could raise between the two, leaving an orphan card
   assigned to nobody.
3. The response is the full dossier (§2.2), including the previous worker's
   `released` note. Resuming is the normal case.
"""

from __future__ import annotations

from typing import Any

from . import _args, _facts, _context
from .. import _clock
from .._ids import new_task_id
from ..core import graph, machine
from .._errors import Refused, BadRequest
from ..core.event import make
from ..core.types import Card, Event
from ..store.stores import Stores


def run(stores: Stores, actor: str, args: _args.Args) -> dict[str, Any]:
    now = _clock.now()
    events: list[Event] = []
    title = _args.text(args, "title", default="")
    card = _capture(stores, actor, args, now, events) if title else _pick(stores, actor, args, now)

    branch = _facts.branch_of(card)
    if not events:  # an existing card: the guards apply
        machine.check_take(card, _facts.facts(stores, card, now), actor)
    lease = stores.live.acquire(card["id"], actor, branch, now)
    if lease is None:
        holder = stores.live.holder(card["id"], now)
        raise Refused(
            f"{card['id']} was claimed by {holder} a moment ago. Run taskops_board to see "
            "what is waiting for you."
        )
    if card["assignee"] != actor:
        # `claimed` records WHOSE it is. Being on it right now is the lease's
        # answer, and the lease was just written above.
        events.append(make(card["id"], actor, "claimed", {"branch": branch}, now))
    stores.write(events)
    stores.live.renew(actor, now)
    return _context.dossier(stores, actor, _facts.find(stores, card["id"]), now)


def _pick(stores: Stores, actor: str, args: _args.Args, now: float) -> Card:
    """Named card, else mine, else the pool. Never a card somebody else owns."""
    task = _args.ident(args, "task", default="")
    if task:
        return _facts.find(stores, task)
    cards = stores.state()["cards"]
    live = _facts.holders(stores, now)
    ours = graph.mine(cards, actor, live)
    if ours:
        return ours[0]
    pool = graph.ready(cards, live)
    if not pool:
        raise Refused(
            "nothing is ready for you: every open card is blocked, assigned or done. "
            "Ask the orchestrator for a dispatch (taskops_assign), or report what you "
            "found with taskops_update."
        )
    return pool[0]


def _capture(stores: Stores, actor: str, args: _args.Args, now: float, events: list[Event]) -> Card:
    """Already mid-edit with no card: create one and claim it, atomically."""
    stone = _facts.open_milestone(stores)
    given = _args.text(args, "milestone", default="")
    if given:
        found = stores.state()["milestones"].get(given)
        if found is None:
            raise BadRequest(f"milestone {given} does not exist")
        stone = found
    if stone is None:
        raise BadRequest(
            "this board has no single open milestone, so a captured card would have no "
            "home — pass milestone=<ms-id>, or ask the orchestrator to open one."
        )
    card = Card(
        id=new_task_id(),
        title=_args.text(args, "title"),
        spec=_args.text(args, "spec", default=""),
        criteria=_args.strings(args, "criteria"),
        status="open",
        priority=_args.number(args, "priority", default=2, low=0, high=3),
        milestone=stone["id"],
        parent=None,
        after=[],
        files=_args.strings(args, "files"),
        labels=_args.strings(args, "labels"),
        assignee=actor,
        created_by=actor,
        created=now,
        updated=now,
    )
    events.append(make(card["id"], actor, "created", {"card": dict(card)}, now))
    return card
