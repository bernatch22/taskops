"""Fold an event stream into board state. Pure, additive, idempotent.

Three properties, each one a v1 bug:

1. **Sort by `(ts, id)` BEFORE applying.** v1 applied in file order, so a
   `status` that arrived before its `created` was dropped until someone
   rebuilt by hand.
2. **Re-apply what said "no such card yet".** Clock skew between two machines
   reorders events that a sort cannot fix; deferred events get another pass.
3. **Newer-wins on `updated`.** Two writers, the later fact stands — and
   replaying the same log twice changes nothing.
"""

from __future__ import annotations

from typing import Any, TypedDict, cast

from .types import KINDS, PROJECT, EDITABLE, CARD_STATUSES, Card, Event, Milestone

_EPS = 1e-9


class State(TypedDict):
    cards: dict[str, Card]
    milestones: dict[str, Milestone]


def empty() -> State:
    return State(cards={}, milestones={})


def fold(events: list[Event], state: State | None = None) -> State:
    """Apply every event in `(ts, id)` order, retrying the ones that arrived early."""
    board = state if state is not None else empty()
    # Sort by time ONLY, and rely on the sort being stable: two events stamped
    # in the same instant keep the order they arrived in (log order = `seq`
    # order — the caller always passes them that way). Breaking that tie by
    # event id instead is arbitrary, and it showed up as a claim landing after
    # the release that undid it, differently on each rebuild.
    ordered = sorted(events, key=lambda e: e["ts"])
    deferred = [e for e in ordered if not apply(board, e)]
    while deferred:
        # `force`: a deferred event is not stale, it arrived early. Judging it by
        # the card's `updated` would drop exactly the events this pass exists for.
        again = [e for e in deferred if not apply(board, e, force=True)]
        if len(again) == len(deferred):
            break  # nothing moved: these events name cards that truly do not exist
        deferred = again
    return board


def apply(state: State, event: Event, *, force: bool = False) -> bool:
    """Apply one event. Returns False if it must be retried after its card exists."""
    kind = KINDS.get(event["kind"])
    if kind is None or not kind.replayed:
        return True  # history-only (comment, commit, merged) or from a newer version
    if event["kind"] == "milestone":
        _milestone(state, event)
        return True
    if event["kind"] == "created":
        return _created(state, event)
    card = state["cards"].get(event["task"])
    if card is None:
        return event["task"] == PROJECT  # a board-level fact has no card to move
    if not force and event["ts"] + _EPS < card["updated"]:
        return True  # a stale fact: something newer already moved this card
    _mutate(card, event)
    card["updated"] = event["ts"]
    return True


def _created(state: State, event: Event) -> bool:
    raw: object = event["body"].get("card")
    if not isinstance(raw, dict):
        return True
    card = cast("dict[str, Any]", raw)
    ident = str(card.get("id") or event["task"])
    state["cards"].setdefault(ident, _coerce_card(ident, card, event))
    return True


def _mutate(card: Card, event: Event) -> None:
    body = event["body"]
    if event["kind"] == "claimed":
        # Who it is FOR. Whether anybody is on it right now is the lease's
        # answer, and the lease is not in the log.
        card["assignee"] = event["actor"]
    elif event["kind"] == "released":
        card["assignee"] = ""
    elif event["kind"] == "status":
        card["status"] = str(body.get("to", card["status"]))
        card["assignee"] = ""  # closed or reopened, it belongs to nobody
    elif event["kind"] == "edited":
        field = str(body.get("field", ""))
        if field in EDITABLE:
            card[field] = body.get("to")  # type: ignore[literal-required]


def _milestone(state: State, event: Event) -> None:
    body = event["body"]
    ident = str(body.get("id") or event["id"])
    op = body.get("op")
    if op == "create":
        state["milestones"].setdefault(
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
    stone = state["milestones"].get(ident)
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


def _coerce_card(ident: str, raw: dict[str, Any], event: Event) -> Card:
    """A `created` body is data from the wire: give every field a typed home."""
    return Card(
        id=ident,
        title=str(raw.get("title", "")),
        spec=str(raw.get("spec", "")),
        criteria=[str(x) for x in raw.get("criteria", []) if x],
        # A status from an older board (or a newer one) that is not one of the
        # three is read as `open` — never invented, never trusted.
        status=str(raw.get("status", "open")) if raw.get("status") in CARD_STATUSES else "open",
        # A board written before review existed has no key: it reads as False.
        review=bool(raw.get("review", False)),
        priority=int(raw.get("priority", 2)),
        milestone=str(raw.get("milestone", "")),
        parent=str(raw["parent"]) if raw.get("parent") else None,
        after=[str(x) for x in raw.get("after", []) if x],
        files=[str(x) for x in raw.get("files", []) if x],
        labels=[str(x) for x in raw.get("labels", []) if x],
        assignee=str(raw.get("assignee", "")),
        created_by=str(raw.get("created_by", event["actor"])),
        created=float(raw.get("created", event["ts"])),
        updated=float(raw.get("updated", event["ts"])),
    )
