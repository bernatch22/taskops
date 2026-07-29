"""`taskops_dispatch` — one agent launches others and hands each a card.

The flow this exists for, and the one taskops could not express before:

```
   planner ──▶ taskops_plan      five cards, wired
           ──▶ taskops_dispatch  five workers, one card each, running now
```

Before this, a planner could create work and then nothing happened: cards sat in a pool waiting for a
human to open a terminal per agent. Assignment alone would not have fixed it either — an assigned card
with nobody running is still a card nobody is doing.

**It PREPARES; the orchestrator spawns.** This assigns the cards, makes their worktrees, and hands
back a ready-to-use brief per card — and starts no process, ever. The caller passes each brief to
its OWN sub-agent tool, so the workers run inside the session that is already open.

There used to be a `spawn=True` that started one `claude -p` per card, and it is gone. It opened a
NEW billed session each time — a real fleet of six drained a balance mid-run and left six cards
claimed by processes that no longer existed — and it could not even deliver what it promised: the
detached worker got a generic prompt and the shell's default model, so a project's registered
specialist, its model and its tool list never reached the worker that was supposed to BE it. A
sub-agent of the current session gets all three, costs what the subscription already paid for, and
dies with the session instead of outliving it invisibly.

**Assign, then hand over, in that order.** The card is assigned to the worker's actor id BEFORE
anything can claim it, so the scheduler will only ever offer it to that worker — and no other agent
sees it at all.

**Concurrency is capped and the cap is low.** Each worker is a model doing unsupervised work in a
repository, so the default is conservative and the ceiling is explicit rather than "as many as you
asked for". A planner that wants twenty has to say twenty.
"""

from __future__ import annotations

from pathlib import Path

from .._errors import BadRequest
from ..contracts import Task
from ..engine import branch_for, unblock
from ..engine.worker import Launched
from ..storage import Store
from ._handoff import assign_worker, route_of
from ._project import caller, heartbeat, project

__all__ = ["dispatch", "DispatchResult", "MAX_WORKERS", "DEFAULT_WORKERS"]

DEFAULT_WORKERS = 3
"""How many launch when nobody says. Three is enough to see parallelism and few enough that a first
try on a real repository cannot turn into a stampede."""

MAX_WORKERS = 12
"""The ceiling, whatever was asked for. Every worker is a Claude Code process with a model behind it,
so the real limits are rate limits and money — and a planner that miscounts should hit a refusal here
rather than an invoice."""


class DispatchResult:
    """Who was launched, and who was not.

    `skipped` is not an afterthought: a dispatch that quietly launched three of five would leave a
    planner believing five agents are working, and the two cards it never started would look claimed
    and never move.
    """

    def __init__(self, *, launched: list[Launched], skipped: list[str],
                 planned: bool = False, spawned: bool = False) -> None:
        self.launched = launched
        self.skipped = skipped
        self.planned = planned
        """True for a dry run. The renderer says so loudly — a preview that reads like a result is
        how somebody believes five agents are working when none are."""

        self.spawned = spawned
        """True when processes were actually started. False in the default mode, where the cards are
        assigned and briefed and the CALLER is expected to spawn sub-agents — so the renderer has to
        tell it that the remaining half is its job."""


def dispatch(start: Path | str, *, tasks: tuple[str, ...] = (), count: int = 0, actor: str = "",
             prefix: str = "", dry_run: bool = False) -> DispatchResult:
    """Prepare a worker per card. Named cards, or the best `count` ready ones.

    `count` rather than "everything ready" as the default shape, because "all" is the request nobody
    means literally on a board with forty cards in it.

    `dry_run` shows the plan and changes NOTHING — no assignment, no worktree. It stays after the
    spawn path was removed because the cost did not go away, it moved: each brief becomes a
    sub-agent the caller pays for, and a planner that miscounted should be able to look before it
    commits to five of them. It is also the honest answer to "which cards would you pick", which no
    amount of reading the scheduler gives you.
    """
    with project(start) as store:
        who = caller(store, actor)
        heartbeat(store, who["id"])
        unblock(store)
        chosen, skipped = _choose(store, tasks, count, who["id"])
        if dry_run:
            return DispatchResult(launched=[_preview(store, t, who["dev"], prefix or "w", i)
                                            for i, t in enumerate(chosen, start=1)],
                                  skipped=skipped, planned=True)
        # The actor name is DERIVED (`agent:<dev>/<prefix><n>`) rather than random, so a fleet
        # view reads as `berna/w1 … berna/w3` instead of three hashes and a developer can tell
        # at a glance which workers are theirs. `_handoff.assign_worker` does the rest.
        prepared = [assign_worker(store, task, f"agent:{who['dev']}/{prefix or 'w'}{i}")
                    for i, task in enumerate(chosen, start=1)]
        return DispatchResult(launched=prepared, skipped=skipped)


def _preview(store: Store, task: Task, dev: str, prefix: str, index: int) -> Launched:
    """What a worker WOULD be. pid 0 says no process exists, which the renderer reads."""
    from ..engine.worker import worktree_for

    return Launched(actor=f"agent:{dev}/{prefix}{index}", task=task["id"], pid=0,
                    tree=worktree_for(store.root, task), log=Path(""),
                    branch=branch_for(task), brief="", agent_type=route_of(store.root, task))


def _choose(store: Store, wanted: tuple[str, ...], count: int,
            asker: str) -> tuple[list[Task], list[str]]:
    """The cards to dispatch, and the ids that were refused with a reason attached to none.

    A named card must be `ready`, unassigned, AND carry a spec — the same rules `next` enforces
    plus one this call needs for itself: a worker is a model spending money unsupervised, and one
    handed a title with no spec cannot do anything but guess or give up. Both happened to one
    card in one day: two workers dispatched, two releases, zero work. The human who can write
    the spec needs a minute; the worker who cannot invent it needs none of ours.
    """
    from ..engine import ready_tasks

    if wanted:
        found = [store.tasks.need(task_id) for task_id in wanted]
        ok = [t for t in found
              if t["status"] == "ready" and not t["assignee"] and t["spec"].strip()]
        return _capped(ok), [t["id"] for t in found if t not in ok]
    pool = [t for t in ready_tasks(store, actor=asker) if t["spec"].strip()]
    return _capped(pool[:count or DEFAULT_WORKERS]), []


def _capped(tasks: list[Task]) -> list[Task]:
    if len(tasks) > MAX_WORKERS:
        raise BadRequest(f"{len(tasks)} workers asked for; the ceiling is {MAX_WORKERS} — "
                         f"dispatch in batches, or raise it deliberately")
    return tasks
