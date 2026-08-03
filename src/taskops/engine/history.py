"""The log read as a HISTORY: what happened here, in order, and who did it.

Its own module rather than a third projection in `activity.py`, because it answers a different
question. That one is about the workers as they are right now — who holds what, is it alive — and
this one is about the record they leave behind, which outlives every session that wrote it.

Nothing is stored for it. Every fact it shows is already in `events.jsonl`, which is why it could be
added without a migration and why it cannot drift from what actually happened.
"""

from __future__ import annotations

from ..contracts import Activity, ActorRoll, Event
from ..contracts.context import CONTEXT_TASK
from ..storage import Store
from .activity import tasks_of
from .timespent import attended, stretches

__all__ = ["activity", "rolls", "MAX_EVENTS"]

MAX_EVENTS = 600
"""How much timeline one read returns. A window wide enough to be interesting on an old project is
also wide enough to be tens of thousands of events, and nobody scrolls that — so it is bounded, and
the answer SAYS it was bounded rather than quietly showing a slice as if it were everything."""


def activity(store: Store, *, since: float, until: float = 0.0,
             limit: int = MAX_EVENTS) -> Activity:
    """The timeline, plus a roll-up per actor, from one pass over the same events.

    One projection and not two: a per-actor summary computed over a different window than the
    timeline beside it would summarise something the reader cannot see, and it would cost a second
    scan of the same rows to be wrong.

    The questions this answers — when did this card really move, who has ever touched this area,
    what did that agent do while it held the lease — are answerable from the log and from nothing
    else, because a task row keeps only where things landed.
    """
    # The whole RANGE, folded — and only the TIMELINE capped. The roll-ups (who did what, how long,
    # what was open at once) are what a profile reads, and a total that came out short because the
    # 601st event did not fit is a wrong number rather than a bounded one. Nobody scrolls ten
    # thousand rows, so the list stays capped and `truncated` says the list was.
    #
    # This is not the "two windows" mistake the docstring above warns about: both halves are folded
    # over exactly the same range. One of them is displayed in full and the other is not.
    found = store.events.between(since, until)
    kept = found[-limit:] if len(found) > limit else found
    return Activity(repo=str(store.root), since=since, events=list(reversed(kept)),
                    # `CONTEXT_TASK` gets a title of its own. It is the sentinel a fact and a
                    # milestone are filed under — an `Event` must name a task and these are about
                    # the project — so the timeline has rows whose "card" is not a card, and a
                    # feed that looked them up found nothing and rendered a bare `project`.
                    titles={**({CONTEXT_TASK: "the project itself"}
                               if any(e["task"] == CONTEXT_TASK for e in kept) else {}),
                            **{task["id"]: task["title"]
                               for task in tasks_of(store, [e["task"] for e in kept])}},
                    actors=rolls(found), kinds=sorted({e["kind"] for e in kept}),
                    truncated=len(found) > limit)


def rolls(events: list[Event]) -> list[ActorRoll]:
    """Per actor, busiest first. Public because `day` needs the same roll-up over its own
    window — two projections summarising actors two different ways is exactly how a board
    starts disagreeing with itself about who did what.

    Counted from the events rather than from leases, which is what makes an agent that finished an
    hour ago still appear: the lease is gone, the work is not. That is the whole reason this replaced
    a live fleet panel — "who is free" stopped being a question when agents became disposable.
    """
    seen: dict[str, list[Event]] = {}
    for event in events:
        seen.setdefault(event["actor"], []).append(event)
    out = [_roll(actor, theirs) for actor, theirs in seen.items()]
    return sorted(out, key=lambda roll: (-roll["tasks"], -roll["commits"], roll["actor"]))


def _roll(actor: str, events: list[Event]) -> ActorRoll:
    """Tasks, not events: an actor that commented forty times on one card has done less than one
    that closed four, and counting events would rank them the other way round."""
    stamps = [event["ts"] for event in events]
    kinds = [event["kind"] for event in events]
    return ActorRoll(actor=actor, tasks=len({event["task"] for event in events}),
                     commits=kinds.count("commit"),
                     comments=kinds.count("comment") + kinds.count("message"),
                     # A close is its OWN kind — `update` writes `done` rather than `status` when
                     # the target is done, precisely so it can be found without reading bodies.
                     # This is the only place the fact lives: the task row shows the state, never
                     # who moved it there.
                     done=kinds.count("done"),
                     # Over the SAME events as every count above it. A time roll-up computed on its
                     # own window would summarise something the reader cannot see beside it, which
                     # is the mistake this module's docstring already argues against once.
                     on=attended(events), sittings=stretches(events),
                     first_seen=min(stamps), last_seen=max(stamps))
