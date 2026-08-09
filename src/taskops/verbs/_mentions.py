"""The ✉ half of the board: who was named and has not answered since.

Split out of `pulse.py` when it outgrew the 200-line budget, and split HERE
because this is where the seam already was: `core/mentions.py` already owns
the derivation, and the
`mentions` verb exists for one caller that `board` cannot serve — the delivery
hook, which reads on somebody else's behalf and must therefore not renew a
lease. Everything here is that one concern.

Nothing is stored and nothing is marked read: answering on the card IS the
clearing, which is why there is no ack verb (ARCHITECTURE.md §11).
"""

from __future__ import annotations

from typing import Any

from . import _args, _facts
from .. import _clock
from ..store.stores import Stores


def mentions(stores: Stores, actor: str, args: _args.Args) -> dict[str, Any]:
    """The ✉ group alone, for ONE reader, and WITHOUT renewing anything.

    `taskops hook claude` calls this on a tool call the reader
    did not make itself, so it must be a read in the strictest sense. `board`
    would not do: it opens with `live.renew(actor)`, which is right for a call
    the actor typed — that call IS the heartbeat — and wrong here. A hook firing
    on the orchestrator's `Read` of a dead worker's worktree would renew THAT
    worker's lease, and the card it abandoned would never reach STALLED. That is
    a stored `doing` grown back by the side door, which is the one thing this
    board is built not to have.

    `for_task=` is how a hook that knows the card asks who it belongs to; see
    `_addressee`. The answer names the actor it resolved, because the caller
    could not have known it.
    """
    who = _addressee(stores, args) or actor
    return {"actor": who, "mentions": rows(stores, who)}


def _addressee(stores: Stores, args: _args.Args) -> str:
    """Whose ✉ a card carries: its live holder, else whoever it was handed to.

    A hook process does not inherit the worker's environment, so it cannot read
    `TASKOPS_ACTOR` off a sub-agent — but every tool call that sub-agent makes
    touches its own worktree, the worktree is named after the card, and the card
    is named here. That chain is what makes delivery to a sub-agent possible at
    all. An unknown card, or one nobody owns, answers "" so the caller falls
    back to its own identity rather than to a guess.
    """
    task = _args.ident(args, "for_task", default="")
    card = stores.state()["cards"].get(task) if task else None
    if card is None:
        return ""
    return stores.live.holder(task, _clock.now()) or card["assignee"]


def rows(stores: Stores, actor: str) -> list[dict[str, Any]]:
    """The one group the milestone filter does not apply to: a mention is
    addressed to a person, not to a chapter, and a reader focused elsewhere is
    exactly who must not miss it.

    The card's title travels with it like it does in every other group — an id
    is not something a reader recognises without spending another call.
    """
    cards = stores.state()["cards"]
    return [
        {
            "id": m["task"],
            "title": cards[m["task"]]["title"] if m["task"] in cards else "",
            "by": m["by"],
            "text": m["text"],
            "ts": m["ts"],
        }
        for m in _facts.pending_mentions(stores, actor)
    ]


