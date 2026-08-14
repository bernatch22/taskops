"""The CHAPTER half of `update` — `taskops_update milestone=` with no task=.

Split out of `update.py` at the seam that was always there: everything else in
that module changes a CARD (and shares its guards, its lease release and its
derived state), while this changes a MILESTONE and shares none of them. The two
halves only ever met at one `if` on the first line of `run`.

Nothing about the shape changed in the move. Every list field is replaced WHOLE
— `rules`, `criteria` and `union_files` alike — because an append-only edit
would leave no way to withdraw one short of a `retire` event, which is the
machinery this deliberately does not have (`core/chapters.py` folds them the
same way). And the branch never moves: it was computed once at creation and
stored, so renaming a chapter cannot move it under the worktrees living on it.
"""

from __future__ import annotations

from typing import Any

from . import _args, _context
from .._errors import NotFound, BadRequest
from ..core.event import make
from ..core.types import PROJECT
from ..store.stores import Stores

# The chapter's list fields, each replaced whole. `union_files` is the seam
# declaration `gitwork/catchup.py` reads at a card's catch-up merge.
LISTS = ("rules", "criteria", "union_files")


def run(stores: Stores, actor: str, args: _args.Args, now: float) -> dict[str, Any]:
    """Close or retitle a chapter, or replace one of its declarations."""
    ident = _args.text(args, "milestone")
    stone = stores.state()["milestones"].get(ident)
    if stone is None:
        raise NotFound(f"milestone {ident} does not exist")
    body: dict[str, Any] = {"id": ident}
    status = _args.text(args, "status", default="")
    if status:
        if status not in ("open", "done", "dropped"):
            raise BadRequest("a milestone is open, done or dropped")
        body.update({"op": "status", "to": status})
    else:
        body["op"] = "edit"
        for field in ("title", "goal"):
            if field in args:
                body[field] = _args.text(args, field)
        for field in LISTS:
            if field in args:
                body[field] = _args.strings(args, field)
        if "reviews" in args:
            body["reviews"] = _args.flag(args, "reviews")
        if len(body) == 2:
            raise BadRequest(
                "nothing to change: pass status=, title=, goal=, rules=, criteria=, "
                "union_files= or reviews="
            )
    seq = stores.write([make(PROJECT, actor, "milestone", body, now)])
    stores.live.renew(actor, now)
    return {
        "milestone": stores.state()["milestones"][ident],
        "seq": seq,
        "pulse": _context.pulse(stores, actor, now, ident),
    }
