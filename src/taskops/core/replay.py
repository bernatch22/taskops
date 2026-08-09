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

from . import chapters
from .types import KINDS, PROJECT, EDITABLE, CARD_STATUSES, Card, Event, Milestone

_EPS = 1e-9


class State(TypedDict):
    cards: dict[str, Card]
    milestones: dict[str, Milestone]

    # Facts about the BOARD's repo, one entry per `op` — today just `remote`.
    # A project fact has no card, so it has no `updated` to arbitrate with: the
    # arbiter is `project_at`, per op, and property 3 holds through it.
    project: dict[str, Any]
    project_at: dict[str, float]


def empty() -> State:
    return State(cards={}, milestones={}, project={}, project_at={})


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
        chapters.fold(state["milestones"], event)
        return True
    if event["kind"] == "project":
        _project(state, event)
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


def _project(state: State, event: Event) -> None:
    """Newest-wins, per `op` — property 3 of this module, for a fact with no card.

    An older event arriving late (another clone's log, a rebuild) must not undo
    a newer one, exactly as `apply` refuses a stale card fact. `value: None`
    is a legal value and clears the fact; the timestamp still moves, so the
    clearing cannot be resurrected by a replay of what it withdrew.
    """
    op = str(event["body"].get("op", ""))
    if not op or event["ts"] + _EPS < state["project_at"].get(op, float("-inf")):
        return
    state["project"][op] = event["body"].get("value")
    state["project_at"][op] = event["ts"]


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
