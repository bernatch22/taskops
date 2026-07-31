"""Choosing, capping and assigning workers — the half of a dispatch that runs ANYWHERE.

Split from `dispatch` when remote projects arrived, and the seam is where each half can
possibly run. `pick` chooses and assigns, and must run where the truth lives — with a remote,
the server — because a choice made against a stale board hands one card to two fleets.
`prepared` makes worktrees and briefs, and can only run where the git checkout lives — the
developer's machine. `dispatch` composes them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .._errors import BadRequest
from ..contracts import Task
from ..engine import branch_for, unblock
from ..engine.worker import Launched, prepare, worktree_for
from ._handoff import hand_over
from ._project import caller, heartbeat, locate, project

__all__ = ["pick", "prepared", "DispatchResult", "DEFAULT_WORKERS", "MAX_WORKERS"]

DEFAULT_WORKERS = 3
"""How many launch when nobody says. Three is enough to see parallelism and few enough that a
first try on a real repository cannot turn into a stampede."""

MAX_WORKERS = 12
"""The ceiling, whatever was asked for. Every worker is a Claude Code process with a model
behind it, so the real limits are rate limits and money — and a planner that miscounts should
hit a refusal here rather than an invoice."""


class DispatchResult:
    """Who was launched, and who was not.

    `skipped` is not an afterthought: a dispatch that quietly launched three of five would
    leave a planner believing five agents are working, and the two cards it never started
    would look claimed and never move.
    """

    def __init__(self, *, launched: list[Launched], skipped: list[str],
                 planned: bool = False, spawned: bool = False) -> None:
        self.launched = launched
        self.skipped = skipped
        self.planned = planned
        """True for a dry run. The renderer says so loudly — a preview that reads like a
        result is how somebody believes five agents are working when none are."""

        self.spawned = spawned
        """True when processes were actually started. False in the default mode, where the
        cards are assigned and briefed and the CALLER is expected to spawn sub-agents."""


def pick(start: Path | str, *, tasks: tuple[str, ...] = (), count: int = 0, actor: str = "",
         dry_run: bool = False) -> dict[str, Any]:
    """Choose and ASSIGN the best cards — the rpc verb behind a remote dispatch.

    Workers are named after the ASKER's dev (`agent:<dev>/wN`), which the caller sends
    resolved: the server cannot read a remote machine's git config.
    """
    with project(start) as store:
        store.claiming()      # choose-then-assign is read-decide-write; same law as `claim`
        who = caller(store, actor)
        heartbeat(store, who["id"])
        unblock(store)
        chosen, skipped = _choose(store, tasks, count, who["id"])
        names = [f"agent:{who['dev']}/w{i}" for i in range(1, len(chosen) + 1)]
        if not dry_run:
            for task, worker in zip(chosen, names, strict=True):
                hand_over(store, task["id"], worker, actor=worker, dispatched=True)
        return {"chosen": chosen, "workers": names, "skipped": skipped, "planned": dry_run}


def prepared(start: Path | str, picked: dict[str, Any], *, dry_run: bool) -> DispatchResult:
    """The local half of a remote dispatch: worktrees, branches and briefs for cards the
    SERVER already chose and assigned."""
    from .agents import agent_for

    root = locate(start)
    launched: list[Launched] = []
    for task, worker in zip(picked["chosen"], picked["workers"], strict=True):
        if dry_run:
            launched.append(Launched(actor=worker, task=task["id"], pid=0,
                                     tree=worktree_for(root, task), log=Path(""),
                                     branch=branch_for(task), brief="",
                                     agent_type=agent_for(root, task["labels"])))
            continue
        started = prepare(root, task, actor=worker)
        started.agent_type = agent_for(root, task["labels"])
        launched.append(started)
    return DispatchResult(launched=launched, skipped=list(picked.get("skipped", [])),
                          planned=dry_run)


def _choose(store: Any, wanted: tuple[str, ...], count: int,
            asker: str) -> tuple[list[Task], list[str]]:
    """The cards to dispatch, and the ids that were refused with a reason attached to none.

    A named card must be `ready`, unassigned, AND carry a spec — the same rules `next`
    enforces plus one this call needs for itself: a worker is a model spending money
    unsupervised, and one handed a title with no spec cannot do anything but guess or give
    up. Both happened to one card in one day.
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
