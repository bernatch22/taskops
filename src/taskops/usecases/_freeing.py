"""Freeing one stuck card, and writing down what its worker left behind.

Split from `recover` because that module DECIDES what is stuck and this one does the freeing. The note
each of these writes is the part that matters most: a card that comes back with no explanation looks
like a card nobody ever started, and the next agent rewrites from zero the file sitting in a directory
two levels down. It names the PATH — "partial work exists" sends an agent looking, a path sends it
reading.
"""

from __future__ import annotations

from pathlib import Path

from .._clock import now
from ..contracts import Lease
from ..engine import record
from ..engine.gitstate import porcelain
from ..engine.worker import worktree_for
from ..storage import Store

__all__ = ["release_lease", "unassign", "Stuck"]


class Stuck:
    """One card that was recovered, and what was left behind in its worktree."""

    def __init__(self, *, task: str, actor: str, silent_for: float, commits: int,
                 leftovers: list[str], tree: Path) -> None:
        self.task = task
        self.actor = actor
        self.silent_for = silent_for
        self.commits = commits
        """Commits already bound to the card. These SURVIVE — they are in git."""

        self.leftovers = leftovers
        """Uncommitted paths in the worker's worktree. The part that is easy to lose."""

        self.tree = tree


def release_lease(store: Store, lease: Lease, who: str, quiet: float) -> Stuck:
    """Hand one card back, and write down what its worker left in the tree.

    The comment is the whole point of doing this here rather than leaving it to the lease timer: a
    card that came back with no explanation looks like a card nobody ever started, and the next agent
    rewrites from zero the file that is sitting in a directory two levels down.
    """
    tree = worktree_for(store.root, store.tasks.need(lease["task"]))
    leftovers = porcelain(tree)
    commits = len(store.events.of_task(lease["task"], kinds=("commit",)))
    store.leases.release(lease["task"])
    store.tasks.set_status(lease["task"], "ready", when=now())
    store.tasks.set_assignee(lease["task"], "", when=now())
    record(store, task=lease["task"], actor=who, kind="released",
           body={"text": _note(lease, quiet, commits, leftovers, tree),
                 "recovered_from": lease["actor"], "leftovers": leftovers})
    return Stuck(task=lease["task"], actor=lease["actor"], silent_for=quiet,
                 commits=commits, leftovers=leftovers, tree=tree)


def unassign(store: Store, task_id: str, assignee: str, who: str) -> Stuck:
    """Free a card whose worker was never started. Same bookkeeping, different reason."""
    tree = worktree_for(store.root, store.tasks.need(task_id))
    leftovers = porcelain(tree)
    commits = len(store.events.of_task(task_id, kinds=("commit",)))
    store.tasks.set_assignee(task_id, "", when=now())
    record(store, task=task_id, actor=who, kind="released",
           body={"text": f"Recovered: assigned to {assignee}, which never started. "
                         f"Back in the open pool."
                         + (f" UNCOMMITTED work survives in {tree}: {', '.join(leftovers)}."
                            if leftovers else ""),
                 "recovered_from": assignee, "leftovers": leftovers, "never_started": True})
    return Stuck(task=task_id, actor=assignee, silent_for=0.0, commits=commits,
                 leftovers=leftovers, tree=tree)


def _note(lease: Lease, quiet: float, commits: int, leftovers: list[str],
          tree: Path) -> str:
    """The comment left on the card. Written for whoever picks it up next.

    It names the PATH, not just the fact that something is there: "partial work exists" sends the
    next agent looking, and a path sends it reading.
    """
    lines = [f"Recovered: {lease['actor']} went silent for {int(quiet // 60)}m and the card was "
             f"handed back."]
    if commits:
        lines.append(f"{commits} commit(s) are already bound to it and are safe in git.")
    if leftovers:
        lines.append(f"UNCOMMITTED work survives in {tree}: {', '.join(leftovers)}. "
                     f"Read it before starting from scratch.")
    else:
        lines.append("Nothing uncommitted was left behind.")
    return " ".join(lines)
