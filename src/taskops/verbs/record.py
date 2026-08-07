"""record — the two writes that register something that happened outside.

`bind` is called by the `post-commit` git hook: the commit already exists, and
this is what puts it on the card. It is the fact the `done` guard asks for.
`merged` is called by the client half of `taskops_merge` after git actually
integrated the branch.

Both are idempotent by construction: the event id is the hash of its content,
so the offline queue in `gitwork/bind.py` can drain twice without duplicating
anything. In v1 a bind that failed while the server was down was lost forever
and the card could never close.
"""

from __future__ import annotations

from typing import Any

from . import _args, _facts, _context
from .. import _clock
from .._errors import Refused
from ..core.event import make
from ..core.types import PROJECT
from ..store.stores import Stores


def bind(stores: Stores, actor: str, args: _args.Args) -> dict[str, Any]:
    """A commit with a card lands on it; a commit WITHOUT one is still recorded,
    on `project`. Nobody is forced to take a card to commit — the board just
    knows that this sha happened outside any card, and that is all it knows."""
    now = _clock.now()
    given = _args.ident(args, "task", default="")
    task = _facts.find(stores, given)["id"] if given else PROJECT
    body: dict[str, Any] = {
        "sha": _args.text(args, "sha"),
        "subject": _args.text(args, "subject", default=""),
        "files": _args.strings(args, "files"),
        "branch": _args.text(args, "branch", default=""),
    }
    ts = _timestamp(args, now)
    seq = stores.write([make(task, actor, "commit", body, ts)])
    stores.live.renew(actor, now)
    return {"task": task, "sha": body["sha"], "seq": seq}


def merged(stores: Stores, actor: str, args: _args.Args) -> dict[str, Any]:
    """The card reached its milestone branch — or, with milestone=, the whole
    milestone reached the trunk. Only the orchestrator integrates."""
    now = _clock.now()
    stone_id = _args.text(args, "milestone", default="")
    if stone_id:
        if stone_id not in stores.state()["milestones"]:
            raise Refused(f"milestone {stone_id} does not exist")
        body: dict[str, Any] = {"op": "landed", "id": stone_id, "into": _args.text(args, "into"),
                                "sha": _args.text(args, "sha")}
        if _args.flag(args, "criteria_met"):
            # The human's out-loud answer to the chapter's criteria, recorded —
            # never judged here (docs/fan-out.md §8B: the board records, the
            # human decides).
            body["criteria_met"] = True
        seq = stores.write([make(PROJECT, actor, "milestone", body, now)])
        stores.live.renew(actor, now)
        return {"milestone": stores.state()["milestones"][stone_id],
                "into": body["into"], "sha": body["sha"], "seq": seq,
                "pulse": _context.pulse(stores, actor, now, stone_id)}
    card = _facts.find(stores, _args.ident(args, "task"))
    if card["status"] != "done":
        raise Refused(
            f"{card['id']} is {card['status']}, not done — half-finished work does not "
            "go into the milestone branch"
        )
    stone = _facts.milestone_of(stores, card)
    into = _args.text(args, "into", default=stone["branch"] if stone else "")
    body = {"into": into, "sha": _args.text(args, "sha")}
    seq = stores.write([make(card["id"], actor, "merged", body, now)])
    stores.live.renew(actor, now)
    return {
        "task": card["id"],
        "into": into,
        "seq": seq,
        "pulse": _context.pulse(stores, actor, now, card["milestone"]),
    }


def _timestamp(args: _args.Args, now: float) -> float:
    """A commit can be bound minutes later, from a queue — keep its own time.

    Clamped to `now` so a machine with a skewed clock cannot push events into
    the future, where nothing that sorts by time would ever see them again.
    """
    given = args.get("ts")
    if isinstance(given, (int, float)) and not isinstance(given, bool):
        return min(float(given), now)
    return now
