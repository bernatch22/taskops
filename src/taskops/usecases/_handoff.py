"""Giving a card to somebody else — the ONE meaning of "assign".

There were two, and that was the bug. `dispatch` assigned with `set_assignee`, which makes the
card invisible to every other agent; `capture(assign=...)` only left a mention, so the card
stayed in the open pool and the next agent to call `next` could take it out from under the
person it had just been given to. Same word in the tool surface, two different outcomes, and
nothing in either reply said which one you got.

So both go through here. Assignment is a FIELD plus a handoff event — never a lease: a lease
belongs to a process that is alive and heartbeating, and one minted for an agent that is not
running lapses fifteen minutes later with nobody watching, having spent that time telling the
board the work was in hand.
"""

from __future__ import annotations

from pathlib import Path

from .._clock import now
from ..contracts import Task
from ..engine import record
from ..engine.worker import Launched, launch, prepare
from ..storage import Store
from .agents import agent_for

__all__ = ["hand_over", "assign_worker", "route_of"]


def hand_over(store: Store, task: str, to: str, *, actor: str = "",
              dispatched: bool = False) -> None:
    """Assign `task` to `to`, and say so in the thread.

    `dispatched` marks the handoffs a fleet made, which is how a reader tells a planner's
    deliberate "this is yours" from three cards a `dispatch` call assigned in one breath.
    The mention rides in the event body so the assignee's inbox pings either way.
    """
    store.tasks.set_assignee(task, to, when=now())
    record(store, task=task, actor=actor or to, kind="handoff",
           body={"assigned_to": to, "dispatched": dispatched, "mentions": [to]})


def assign_worker(store: Store, task: Task, worker: str, *, spawn: bool, model: str,
                  use_api_key: bool) -> Launched:
    """Hand one card to one worker and prepare it — the whole of what `dispatch` does per card.

    Assignment FIRST, always: the card is invisible to everybody else before anything could
    claim it. Then the ROUTE, which rides on the brief rather than on a command line, because
    taskops never spawns anything — it can say "this card is the collectors specialist's", and
    only the host session can act on that. Empty when nothing matches, which is what every
    project without a registry keeps getting.
    """
    hand_over(store, task["id"], worker, actor=worker, dispatched=True)
    kind = agent_for(store.root, task["labels"])
    started = (launch(store.root, task, actor=worker, model=model, use_api_key=use_api_key)
               if spawn else prepare(store.root, task, actor=worker))
    started.agent_type = kind
    if kind and started.brief:
        started.brief += (f"\n\nagent_type: {kind} — spawn this card's sub-agent with THAT agent "
                          f"type; it is the specialist this project registered for these labels.")
    return started


def route_of(root: Path, task: Task) -> str:
    """What a DRY RUN would route to. Changes nothing, which is the dry run's whole promise."""
    return agent_for(root, task["labels"])
