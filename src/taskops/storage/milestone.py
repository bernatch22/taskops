"""The milestone projection: `milestone` events -> the chapters a board is in.

Folded on every read rather than kept in a table, the same call `storage.context` and
`storage.policy` make and for the same reason: the log arrives out of order when a `git pull`
merges two ends of a file, so a stored `state` column would need a repair pass that a fold does
not. There are a handful of chapters on a board, not thousands.

It reads TWO kinds. `milestone` events are the model; `context` events are here only for the
legacy election below, and they are the reason this module knows what an objective is.
"""

from __future__ import annotations

from ..contracts import Event
from ..contracts.context import CONTEXT_KIND, CONTEXT_TASK
from ..contracts.milestone import MILESTONE_KIND, OPEN_MILESTONE, STATES, Milestone, MilestoneState
from ._prefix import matching
from .store import Store

__all__ = ["milestones", "active", "planned", "one"]

_VERIFIED: tuple[MilestoneState, ...] = ("reached", "abandoned")
"""The two moves that write `closed_by`, and `review` is deliberately not among them.

That is the point of the whole model in one line: an agent moving a chapter to `review` is
REPORTING, and the field that says who agreed stays empty until somebody who is not the reporter
moves it to `reached`. A `review` that filled it would make "somebody says it is done" and
"somebody verified it" the same record.
"""


def milestones(store: Store) -> list[Milestone]:
    """Every chapter this board has ever had, oldest first. One indexed scan.

    Creation order and not state order: a reader wants #1 #2 #3 to mean what it means in
    `docs/milestones.md`, and grouping by state is a renderer's decision.
    """
    events = store.events.of_task(CONTEXT_TASK, kinds=(MILESTONE_KIND, CONTEXT_KIND))
    found: dict[str, Milestone] = {}
    for event in (e for e in events if e["kind"] == MILESTONE_KIND):
        _apply(found, event)
    _elect(found, events)
    return sorted(found.values(), key=lambda m: (m["created"], m["id"]))


def active(store: Store) -> list[Milestone]:
    """The chapters being worked on — `in_force` or `review`. SEVERAL is the normal case.

    A list and not an Optional, and that is the correction 0.5.0 makes to its own design note: a
    team ships two things in one fortnight, and a model returning one would have forced the other
    to read `planned` while somebody was demonstrably working on it. What bounds a worker's slice
    is its CARD's milestone, not the board having only one.
    """
    return [m for m in milestones(store) if m["state"] in OPEN_MILESTONE]


def planned(store: Store) -> list[Milestone]:
    """Written down, nobody on it. Titles only in every renderer — see `ContextSlice.planned`."""
    return [m for m in milestones(store) if m["state"] == "planned"]


def one(store: Store, id_or_prefix: str) -> Milestone | None:
    """One chapter by id or by the first characters of it, or None when that names anything else.

    None for BOTH "no such chapter" and "two chapters start with that" — this layer may not pick
    between two, and the caller that has to write the refusal calls `matching` for the list.
    """
    rows = milestones(store)
    hits = matching(rows, id_or_prefix.strip())
    if len(hits) != 1:
        return None
    return next((m for m in rows if m["id"] == hits[0]), None)


def _apply(found: dict[str, Milestone], event: Event) -> None:
    """One `milestone` event, folded in. An op or a target this version cannot read is SKIPPED.

    Skipping rather than raising is the contract the whole log reader keeps: a teammate on a newer
    taskops writes ops this one has never heard of, and one of them must not make the board
    unreadable.
    """
    body = event["body"]
    op = str(body.get("op", ""))
    if op == "create":
        # `planned` and not a `state` field: what a creator decides is whether to START it, and a
        # free-text state in the body would let a create event assert `reached`.
        found[event["id"]] = _born(event, "planned" if body.get("planned") else "in_force")
        return
    current = found.get(str(body.get("milestone", "")))
    if current is None:
        return
    if op == "update":
        for field in ("text", "horizon"):
            if field in body:                   # absent means "leave it", not "blank it"
                current[field] = str(body[field])   # type: ignore[literal-required]
        current["updated"] = event["ts"]
    elif op == "move":
        _move(current, event)


def _born(event: Event, state: MilestoneState) -> Milestone:
    """A chapter as its first event leaves it. Shared by `create` and by the legacy election,
    which differ in the state they arrive in and in nothing else — `closed_by` and `note` are
    empty in both, because neither a creation nor a supersession is somebody verifying anything.
    """
    body = event["body"]
    return Milestone(id=event["id"], text=str(body.get("text", "")),
                     horizon=str(body.get("horizon", "")), state=state,
                     created_by=event["actor"], created=event["ts"], updated=event["ts"],
                     closed_by="", note="")


def _move(current: Milestone, event: Event) -> None:
    """A transition. `planned` is not a destination: nothing un-starts a chapter."""
    to = str(event["body"].get("to", ""))
    if to not in STATES or to == "planned":
        return
    current["state"] = to                       # type: ignore[typeddict-item]
    current["note"] = str(event["body"].get("m", ""))
    current["updated"] = event["ts"]
    if to in _VERIFIED:
        current["closed_by"] = event["actor"]


def _elect(found: dict[str, Milestone], events: list[Event]) -> None:
    """A pre-0.5.0 board's PROJECT objectives, read as the chapters they were.

    No data migration: the boards are not reset (one server board carries 336 events of real
    history), so the mapping lives in the fold. An objective with no owner was the project's
    north, superseded by stating a newer one — which is exactly a chapter that ended, except that
    nothing recorded whether it was reached. So the LATEST becomes the chapter in force and every
    earlier one becomes `reached` with **no verifier**: the record cannot invent one, and an empty
    `closed_by` is the honest way to say "this ended and nobody signed it".

    An objective with an OWNER is a dev's and stays a fact — `storage.context` still returns it.
    The discriminator is `level` being ABSENT: a 0.5.0 writer always states one, so this mapping
    is inert on anything written after the model existed and cannot elect a chapter twice.
    """
    gone = {str(e["body"].get("retires", "")) for e in events}
    old = [e for e in events if e["kind"] == CONTEXT_KIND and e["id"] not in gone
           and _was_the_north(e)]
    for index, event in enumerate(old):
        # `events` is ordered by (ts, seq), so the LAST of them is the one that was in force.
        found[event["id"]] = _born(event, "in_force" if index == len(old) - 1 else "reached")


def _was_the_north(event: Event) -> bool:
    """A project objective written before milestones existed. Retired ones are excluded by the
    caller: a north somebody explicitly withdrew must not come back as a chapter."""
    body = event["body"]
    return (str(body.get("sort", "")) == "objective" and not str(body.get("owner", ""))
            and "level" not in body)
