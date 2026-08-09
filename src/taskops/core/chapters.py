"""The MILESTONE half of the fold — a chapter's own op vocabulary.

Split out of `replay.py` at its own seam: that file folds CARDS (and arbitrates
staleness by `updated`), this one folds a chapter's four ops. It takes the
milestones dict rather than the whole `State` on purpose — it touches nothing
else, and depending on `State` would make `replay` import this file and this
file import `replay`.

Same three properties as `replay.py`: pure, additive, idempotent.
"""

from __future__ import annotations

from .types import Event, Milestone


def fold(milestones: dict[str, Milestone], event: Event) -> None:
    body = event["body"]
    ident = str(body.get("id") or event["id"])
    op = body.get("op")
    if op == "create":
        milestones.setdefault(
            ident,
            Milestone(
                id=ident,
                title=str(body.get("title", "")),
                goal=str(body.get("goal", "")),
                rules=[str(r) for r in body.get("rules", []) if r],
                criteria=[str(c) for c in body.get("criteria", []) if c],
                reviews=bool(body.get("reviews", False)),
                branch=str(body.get("branch", "")),
                status="open",
                created=event["ts"],
            ),
        )
        return
    stone = milestones.get(ident)
    if stone is None:
        return
    if op == "status":
        stone["status"] = str(body.get("to", stone["status"]))
    elif op == "landed":
        # Landing IS closing: `merge milestone=` already refuses while any card
        # is open or unintegrated, so a landed chapter has nothing left to hold
        # open. Found on the first real landing (2026-08-07): this op used to
        # fall through unfolded, the chapter stayed "open" forever, and from the
        # SECOND chapter on `open_milestone` — which answers None for "several"
        # — could never focus again: no Chapter pane, `plan` demanding
        # milestone= on every call, permanently. The event log already carried
        # the truth; the fold just never read it.
        stone["status"] = "landed"
    elif op == "edit":
        for field in ("title", "goal"):
            if field in body:
                stone[field] = str(body[field])  # type: ignore[literal-required]
        if "rules" in body:
            # The WHOLE list, like every other list field: an append-only edit
            # would leave no way to withdraw a rule short of a `retire` event,
            # which is the machinery this deliberately does not have.
            stone["rules"] = [str(r) for r in body["rules"] if r]
        if "criteria" in body:
            # Same shape, same reason: the whole list or nothing.
            stone["criteria"] = [str(c) for c in body["criteria"] if c]
        if "reviews" in body:
            # Only a DEFAULT for cards planned after it: turning it on does not
            # retro-flag a card, and turning it off does not un-flag one. A card
            # carries its own `review`, and that is the fact the guards read.
            stone["reviews"] = bool(body["reviews"])
