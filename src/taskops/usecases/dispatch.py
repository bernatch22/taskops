"""`taskops_dispatch` — one agent launches others and hands each a card.

The flow this exists for, and the one taskops could not express before:

```
   planner ──▶ taskops_plan      five cards, wired
           ──▶ taskops_dispatch  five workers, one card each, running now
```

**It PREPARES; the orchestrator spawns.** This assigns the cards, makes their worktrees, and
hands back a ready-to-use brief per card — and starts no process, ever. The caller passes each
brief to its OWN sub-agent tool, so the workers run inside the session that is already open.

There used to be a `spawn=True` that started one `claude -p` per card, and it is gone. It
opened a NEW billed session each time — a real fleet of six drained a balance mid-run — and it
could not deliver what it promised: the detached worker got a generic prompt and the shell's
default model, so a project's registered specialist never reached the worker meant to BE it.

**With a remote, the CHOICE happens on the server.** Choosing against this machine's cache
would assign against a stale board — the exact collision the routing of `next` exists to
prevent — so `pick` runs there and only the worktrees are made here, where the checkout is.

**Assign, then hand over, in that order.** The card is assigned to the worker's actor id
BEFORE anything can claim it, so the scheduler will only ever offer it to that worker. The
sizing rules (default 3, ceiling 12) live with `pick`, beside the chooser they cap.
"""

from __future__ import annotations

from pathlib import Path

from ..engine import unblock
from ._handoff import assign_worker
from ._project import caller, heartbeat, project
from ._routing import call_remote, whoami
from .pick import DEFAULT_WORKERS, MAX_WORKERS, DispatchResult, _choose, prepared

__all__ = ["dispatch", "DispatchResult", "MAX_WORKERS", "DEFAULT_WORKERS"]


def dispatch(start: Path | str, *, tasks: tuple[str, ...] = (), count: int = 0, actor: str = "",
             prefix: str = "", dry_run: bool = False) -> DispatchResult:
    """Prepare a worker per card. Named cards, or the best `count` ready ones.

    `count` rather than "everything ready" as the default shape, because "all" is the request
    nobody means literally on a board with forty cards in it.

    `dry_run` shows the plan and changes NOTHING — no assignment, no worktree. Each brief
    becomes a sub-agent the caller pays for, and a planner that miscounted should be able to
    look before it commits to five of them.
    """
    picked = call_remote(start, "pick", {"tasks": list(tasks), "count": count,
                                         "actor": whoami(start, actor), "dry_run": dry_run})
    if picked is not None:
        return prepared(start, picked, dry_run=dry_run)
    with project(start) as store:
        who = caller(store, actor)
        heartbeat(store, who["id"])
        unblock(store)
        chosen, skipped = _choose(store, tasks, count, who["id"])
        # The actor name is DERIVED (`agent:<dev>/<prefix><n>`) rather than random, so a fleet
        # view reads as `berna/w1 … berna/w3` and a developer can tell which workers are theirs.
        names = [f"agent:{who['dev']}/{prefix or 'w'}{index}"
                 for index in range(1, len(chosen) + 1)]
        if dry_run:
            picked = {"chosen": chosen, "workers": names, "skipped": skipped}
        else:
            launched = [assign_worker(store, task, worker)
                        for task, worker in zip(chosen, names, strict=True)]
    if dry_run:
        return prepared(start, picked, dry_run=True)
    return DispatchResult(launched=launched, skipped=skipped)
