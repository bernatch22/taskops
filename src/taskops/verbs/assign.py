"""assign — the server half of `taskops_assign`. Orchestrator only.

It writes ownership and nothing else: no git, no worktrees, no spawning. The
client half (`gitwork/trees.py`) cuts the worktrees and `mcp/brief.py` turns
each row below into the brief you paste into a sub-agent. A verb that shelled
out to git is exactly how v1's `recover` came to report paths from a machine
that was not the caller's.

Assigning is not claiming: the card stays `open` with an owner, so it leaves
the pool but the worker still has to `take` it — which is what creates the
lease, in the worker's own process, where the heartbeat lives.
"""

from __future__ import annotations

from typing import Any

from . import _args, _facts, _context
from .. import _clock
from ..core import seams
from ..store import handover
from .._errors import Refused, BadRequest
from ..core.event import make
from ..core.types import Card, Event
from ..store.stores import Stores


def run(stores: Stores, actor: str, args: _args.Args) -> dict[str, Any]:
    now = _clock.now()
    tasks = _args.strings(args, "tasks")
    if not tasks:
        raise BadRequest('tasks=["tk-a1b2c3", …] — taskops_assign hands out cards that already exist')
    names = _names(stores, actor, args, len(tasks), now)
    events: list[Event] = []
    briefs: list[dict[str, Any]] = []
    # The wave over THIS call's cards — advice, computed before anything is
    # written and never consulted again: the assign proceeds either way (the
    # chapter's own rule, "a warning is never a lock"). It rides in each brief so
    # the sub-agent that gets spawned reads it too, not only the orchestrator.
    apart = seams.wave(stores.state()["cards"], tasks)
    held = {row["id"]: row["why"] for row in (apart or {}).get("held", [])}
    for task, name in zip(tasks, names, strict=True):
        card = _facts.find(stores, task)
        _check(card)
        # The hand-over, not a race: `handover.displace` is the whole argument
        # for why the orchestrator does not wait out a lease it knows is dead.
        was = handover.displace(stores.live, card["id"], name, now)
        events.append(make(card["id"], actor, "edited", {"field": "assignee", "to": name}, now))
        briefs.append(_brief(stores, card, name, now) | {"apart": held.get(task), "displaced": was})
    seq = stores.write(events)
    stores.live.renew(actor, now)
    stone = _facts.milestone_of(stores, _facts.find(stores, tasks[0]))
    return {
        "briefs": briefs,
        "seq": seq,
        "pulse": _context.pulse(stores, actor, now, stone["id"] if stone else ""),
    }


def _check(card: Card) -> None:
    """A closed card is the only thing there is nothing to hand out.

    A LIVE lease used to be refused here, which made the clock the authority on
    whether a worker was alive — the bug `store/handover.py` is the post-mortem
    for. Handing over is now always the orchestrator's call to make.
    """
    if card["status"] in ("done", "dropped"):
        raise Refused(f"{card['id']} is {card['status']} — there is nothing to hand out")


def _brief(stores: Stores, card: Card, name: str, now: float) -> dict[str, Any]:
    """Everything the brief needs — including the base branch the worktree is cut from."""
    stone = _facts.milestone_of(stores, card)
    parent = stores.state()["cards"].get(card["parent"] or "")
    return {
        "task": card["id"],
        "title": card["title"],
        "review": bool(card.get("review", False)),
        "spec": card["spec"],
        "criteria": card["criteria"],
        "labels": card["labels"],
        "epic": {"id": parent["id"], "title": parent["title"]} if parent else None,
        "actor": name,
        "branch": _facts.branch_of(card),
        "worktree": _facts.worktree_of(card),
        "base": stone["branch"] if stone else "",
        "milestone": stone["title"] if stone else "",
        "goal": stone["goal"] if stone else "",
        "rules": stone["rules"] if stone else [],
        "files": card["files"],
        "resume": _facts.last_release(stores.events(card["id"])),
        "collisions": _context.collisions(stores, card, now),
    }


def _names(stores: Stores, actor: str, args: _args.Args, count: int, now: float) -> list[str]:
    """`agent:<dev>/w1`, `w2`… reusing the lowest numbers nobody is currently using.

    A worker name is a slot, not a person: it is free again once its card is
    closed and its lease is gone.
    """
    given = _args.strings(args, "workers")
    owner = actor.partition(":")[2]
    if given:
        if len(given) != count:
            raise BadRequest(f"{len(given)} workers= for {count} tasks — pass one name per card")
        return [n if n.startswith("agent:") else f"agent:{owner}/{n}" for n in given]
    busy = {c["assignee"] for c in stores.state()["cards"].values() if c["assignee"]}
    busy |= {lease["actor"] for lease in stores.live.held(now)}
    out: list[str] = []
    number = 1
    while len(out) < count:
        candidate = f"agent:{owner}/w{number}"
        if candidate not in busy:
            out.append(candidate)
            busy.add(candidate)
        number += 1
    return out
