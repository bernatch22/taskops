"""`taskops_dispatch` — one agent launches others and hands each a card.

The flow this exists for, and the one taskops could not express before:

```
   planner ──▶ taskops_plan      five cards, wired
           ──▶ taskops_dispatch  five workers, one card each, running now
```

Before this, a planner could create work and then nothing happened: cards sat in a pool waiting for a
human to open a terminal per agent. Assignment alone would not have fixed it either — an assigned card
with nobody running is still a card nobody is doing.

**It PREPARES; the orchestrator spawns.** By default this assigns the cards, makes their worktrees,
and hands back a ready-to-use brief per card — and starts no process at all. The caller then passes
each brief to its OWN sub-agent tool, so the workers run inside the session that is already open.

That default is a correction. The first version spawned `claude -p` per card, which opens a NEW
billed session each time; a real fleet of six drained an API balance mid-run and left six cards
claimed by processes that no longer existed. Sub-agents in the current session use the subscription
that is already paid for, and they die with the session instead of outliving it invisibly.
`spawn=True` still exists for the case somebody genuinely wants detached workers.

**Assign, then hand over, in that order.** The card is assigned to the worker's actor id BEFORE
anything can claim it, so the scheduler will only ever offer it to that worker — and no other agent
sees it at all.

**Concurrency is capped and the cap is low.** Each worker is a model doing unsupervised work in a
repository, so the default is conservative and the ceiling is explicit rather than "as many as you
asked for". A planner that wants twenty has to say twenty.
"""

from __future__ import annotations

from pathlib import Path

from .._clock import now
from .._errors import BadRequest
from ..contracts import Task
from ..engine import branch_for, record, unblock
from ..engine.worker import Launched, launch, prepare
from ..storage import Store
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
             prefix: str = "", model: str = "", dry_run: bool = False, spawn: bool = False,
             use_api_key: bool = False) -> DispatchResult:
    """Launch a worker per card. Named cards, or the best `count` ready ones.

    `count` rather than "everything ready" as the default shape, because "all" is the request nobody
    means literally on a board with forty cards in it.

    `dry_run` shows the plan and changes NOTHING — no assignment, no worktree, no process. It exists
    because this is the one call in taskops that spends money: every worker is a model, and a planner
    that miscounted should be able to look before it commits to five of them. It is also the honest
    answer to "which cards would you pick", which no amount of reading the scheduler gives you.

    `use_api_key` is the opt-in for billing per token: a spawned worker inherits the environment
    MINUS `worker.DROPPED_ENV`, so it uses the logged-in subscription. Only the CLI passes it.
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
        prepared = [_assign(store, task, who["dev"], prefix or "w", i, spawn=spawn, model=model,
                            use_api_key=use_api_key) for i, task in enumerate(chosen, start=1)]
        if not spawn:
            return DispatchResult(launched=prepared, skipped=skipped, spawned=False)
        return DispatchResult(launched=[w for w in prepared if w.pid],
                              skipped=skipped + [w.task for w in prepared if not w.pid],
                              spawned=True)


def _preview(store: Store, task: Task, dev: str, prefix: str, index: int) -> Launched:
    """What a worker WOULD be. pid 0 says no process exists, which the renderer reads."""
    from ..engine.worker import worktree_for

    return Launched(actor=f"agent:{dev}/{prefix}{index}", task=task["id"], pid=0,
                    tree=worktree_for(store.root, task), log=Path(""),
                    branch=branch_for(task), brief="")


def _choose(store: Store, wanted: tuple[str, ...], count: int,
            asker: str) -> tuple[list[Task], list[str]]:
    """The cards to dispatch, and the ids that were refused with a reason attached to none.

    A named card must be `ready` and unassigned — the same rule `next` enforces, for the same reason:
    dispatching a worker onto a blocked card would start a process that immediately finds nothing to
    do and exits, which reads as a broken dispatch rather than a wrong request.
    """
    from ..engine import ready_tasks

    if wanted:
        found = [store.tasks.need(task_id) for task_id in wanted]
        ok = [t for t in found if t["status"] == "ready" and not t["assignee"]]
        return _capped(ok), [t["id"] for t in found if t not in ok]
    return _capped(ready_tasks(store, actor=asker)[:count or DEFAULT_WORKERS]), []


def _capped(tasks: list[Task]) -> list[Task]:
    if len(tasks) > MAX_WORKERS:
        raise BadRequest(f"{len(tasks)} workers asked for; the ceiling is {MAX_WORKERS} — "
                         f"dispatch in batches, or raise it deliberately")
    return tasks


def _assign(store: Store, task: Task, dev: str, prefix: str, index: int, *,
            spawn: bool, model: str, use_api_key: bool = False) -> Launched:
    """Assign the card and prepare its worktree; spawn a process only if asked.

    Assignment FIRST, always — see the module docstring. The actor name is derived
    (`agent:<dev>/<prefix><n>`) rather than random, so a fleet view reads as `berna/w1 … berna/w3`
    instead of three hashes and a developer can tell at a glance which workers are theirs.
    """
    worker = f"agent:{dev}/{prefix}{index}"
    store.tasks.set_assignee(task["id"], worker, when=now())
    record(store, task=task["id"], actor=worker, kind="handoff",
           body={"assigned_to": worker, "dispatched": True, "mentions": [worker]})
    if spawn:
        return launch(store.root, task, actor=worker, model=model, use_api_key=use_api_key)
    return prepare(store.root, task, actor=worker)
