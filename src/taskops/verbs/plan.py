"""plan — the whole tree in one call. Orchestrator only.

`parent` and `after` accept an index into THIS call's `tasks` list, so a plan
with dependencies is one transaction. In v1 you could split it across calls and
the second call had to use real ids, which is the shape of every board that
ended up with a dangling edge.

Cycles are refused here, at the write. A graph with a cycle makes "ready"
meaningless, and v1 accepted a 2-cycle silently: both cards were invisible in
every list that filtered by it.
"""

from __future__ import annotations

from typing import Any

from . import _args, _cards, _facts, _context
from .. import _clock
from .._ids import new_task_id, is_milestone_id, new_milestone_id
from ..core import graph
from .._errors import NotFound, BadRequest
from ..core.event import make
from ..core.types import PROJECT, Card, Event, Milestone, slugify
from ..store.stores import Stores

ORDER = 0.001  # the spacing between two cards of the same plan call

# A chapter whose work the trunk does not carry yet. `done` counts: finished is
# not landed, and the new branch will not see it either. Only `landed` (it is in
# the trunk) and `dropped` (there is nothing to miss) are silent.
UNLANDED = ("open", "done")


def run(stores: Stores, actor: str, args: _args.Args) -> dict[str, Any]:
    now = _clock.now()
    events: list[Event] = []
    before = dict(stores.state()["milestones"])
    stone = _milestone(stores, actor, args, now, events)
    rows = _args.rows(args, "tasks")
    if not rows:
        raise BadRequest(
            'plan writes a tree: tasks=[{"title": "…", "spec": "…", "files": ["src/x.py"]}] '
            "— use after: <index> to say what waits for what"
        )
    ids = [new_task_id() for _ in rows]
    fresh: dict[str, Card] = {}
    for index, row in enumerate(rows):
        # A millisecond apart, in the order they were written: the plan HAS an
        # order and the pool reads it back through `created`; identical stamps
        # would leave the tie to a random id.
        #
        # Spaced BACKWARDS from now, never forwards. A card stamped in the
        # future is a card whose next edit looks stale to `replay` and is
        # dropped — which is exactly what the dispatch test caught here.
        stamp = now - (len(rows) - 1 - index) * ORDER
        card = _cards.card(row, ids[index], stone, actor, stamp, ids)
        fresh[card["id"]] = card

    combined = dict(stores.state()["cards"]) | fresh
    for card in fresh.values():
        if card["parent"] and card["parent"] not in combined:
            raise NotFound(f"parent {card['parent']} does not exist")
        for dep in card["after"]:
            graph.check_dep(combined, card["id"], dep)

    for card in fresh.values():
        events.append(make(card["id"], actor, "created", {"card": dict(card)}, card["created"]))
    seq = stores.write(events)
    stores.live.renew(actor, now)
    return {
        "milestone": stone,
        "cards": list(fresh.values()),
        "seq": seq,
        "notes": _unlanded(before, stone),
        "pulse": _context.pulse(stores, actor, now, stone["id"]),
    }


def _unlanded(before: dict[str, Milestone], stone: Milestone) -> list[str]:
    """What a NEW chapter will not see, named — a warning, never a refusal.

    A milestone branch is cut from the trunk (`gitwork/trees.py::base_ref`) and
    nothing checks the trunk is current. The Monitor chapter was cut from a
    `master` missing 27 commits of unlanded UI work; a worker found it when its
    worktree had no `ui/` at all, and the repair was hand-rolled git this
    project bans everywhere else (2026-08-07).

    "Unlanded" is knowable two ways: the board's own record, or git — is the
    milestone branch an ancestor of the trunk. `verbs/` may not touch git at
    all (`tests/test_architecture.py` enforces it), so this reads the record:
    a landed chapter is `status: "landed"` since the fold fix, so anything
    still `open` is exactly what the new branch will not carry.

    Opening a second chapter deliberately is normal — refusing would be wrong.
    Being told what the branch will and will not see is the whole value.
    """
    if stone["id"] in before:  # named an existing chapter — nothing was opened
        return []
    others = sorted(
        (m for m in before.values() if m["status"] in UNLANDED), key=lambda m: m["created"]
    )
    if not others:
        return []
    lines = [f'{m["id"]} "{m["title"]}" is {m["status"]} and has not landed.' for m in others]
    lines.append(
        f"{stone['branch']} is cut from the trunk, so it will not see "
        + ("those chapters' work." if len(others) > 1 else "that chapter's work.")
    )
    return lines


def _milestone(
    stores: Stores, actor: str, args: _args.Args, now: float, events: list[Event]
) -> Milestone:
    """Name an existing milestone, or open one. Never guess between several."""
    given = _args.text(args, "milestone", default="")
    if is_milestone_id(given):
        stone = stores.state()["milestones"].get(given)
        if stone is None:
            raise NotFound(f"milestone {given} does not exist")
        return stone
    if given:
        # The same title twice means the same chapter, not a second one with an
        # identical name — and a duplicate would silently split the board in two
        # (two goals, two branches, two "the open milestone" answers).
        for stone in stores.state()["milestones"].values():
            if stone["status"] == "open" and stone["title"] == given:
                return stone
        ident = new_milestone_id()
        stone = Milestone(
            id=ident,
            title=given,
            goal=_args.text(args, "goal", default=""),
            rules=_args.strings(args, "rules"),
            # What the CHAPTER is accepted against — rendered at the landing
            # gate, answered by the human, never judged here (docs/fan-out.md §8B).
            criteria=_args.strings(args, "criteria"),
            # A default for the chapter's cards, not a rule: per-card wins.
            reviews=_args.flag(args, "reviews"),
            # Computed ONCE and stored. Renaming the milestone later cannot move
            # the branch under the worktrees that already live on it.
            branch=f"ms/{slugify(given)}",
            status="open",
            created=now,
        )
        events.append(make(PROJECT, actor, "milestone", {"op": "create", **dict(stone)}, now))
        return stone
    stone = _facts.open_milestone(stores)
    if stone is None:
        raise BadRequest(
            "this board has no single open milestone — say which chapter this is: "
            'taskops_plan milestone="<title>" goal="<why>" tasks=[…]'
        )
    return stone
