"""What to launch for one card, and what to tell it. The piece that makes a fleet real.

Everything else in taskops coordinates agents somebody else started. This starts them — the difference
between "a hundred agents could work in parallel" and a human opening a hundred terminals.

The mechanics of getting a process running live in `_process`; what is decided here is the command,
the tools it may use, the identity it runs as, and the prompt.

**`$TASKOPS_ROOT` is the load-bearing line.** A worker runs in a `git worktree`, which has no
`.taskops/` of its own — so without it a worker would resolve a fresh empty project inside its own
directory and coordinate with nobody. One board, N working trees.
"""

from __future__ import annotations

from pathlib import Path

from ..contracts import Task
from ._process import make_worktree, spawn
from .identity import ENV_ACTOR
from .scheduler import branch_for

__all__ = ["Launched", "launch", "worktree_for", "prompt_for", "WORKERS_DIR", "TREES_DIR",
           "TOOLS"]

WORKERS_DIR = ".taskops/workers"
"""Where a worker's log goes. Under `.taskops/` so one gitignore rule covers it."""

TREES_DIR = ".taskops/trees"
"""Where the worktrees go. INSIDE the repository but gitignored, which is deliberate: next to the
project they are easy to find and easy to delete, and somewhere under /tmp an interrupted worker's
uncommitted work disappears on the next reboot."""

TOOLS = ("Read", "Write", "Edit", "Bash", "Glob", "Grep", "TodoWrite", "mcp__taskops")
"""What a dispatched worker may use. An ALLOWlist, so a new tool is unavailable until somebody adds
it here — the right direction for a process nobody is watching.

`mcp__taskops` is the whole point: a worker that cannot call taskops cannot claim, comment or close.
No `WebFetch` and no `WebSearch` — a background agent reaching the network is a decision for whoever
dispatches it, not a default.
"""


class Launched:
    """A worker that was started, and where to look at it."""

    def __init__(self, *, actor: str, task: str, pid: int, tree: Path, log: Path,
                 branch: str) -> None:
        self.actor = actor
        self.task = task
        self.pid = pid
        self.tree = tree
        self.log = log
        self.branch = branch


def worktree_for(root: Path, task: Task) -> Path:
    return root / TREES_DIR / task["id"]


def prompt_for(task: Task, actor: str = "") -> str:
    """What the worker is told. Short on purpose — the SPEC lives in the task.

    It names the claim explicitly (`task=<id>`), because a worker launched for one card must not go
    shopping in the pool: the card is already assigned to it, and a bare `taskops_next` would hand it
    whatever sorts first.

    It NAMES the worker's actor id, and that is not cosmetic. A dispatched worker that was not told
    who it is invents an identity — one called itself `agent:claude/worker` and claimed a card
    assigned to a different worker, which is exactly the failure `engine.identity` warns about. The
    id is also in `$TASKOPS_ACTOR`, so this is belt and braces on purpose: the environment is what
    the tools read, and the prompt is what stops the model from overriding it with an argument.

    The last sentence is the important one. A background agent that guesses when the spec is wrong
    produces work nobody asked for and a commit somebody has to read; told to release instead, it
    leaves the next agent everything it learned.
    """
    return (f"You are taskops worker `{actor}`. Do NOT use any other actor id — it is already "
            f"set in your environment, so never pass `actor` to a taskops tool. "
            f"Read .taskops/GUIDE.md, then run "
            f"`taskops_next task={task['id']}` to claim your task and read its spec. "
            f"Do the work, commit it on the branch the claim names, then close the task with "
            f"`taskops_update task={task['id']} status=done` and a comment saying what you did. "
            f"If you get stuck or the spec is wrong, do NOT guess: use "
            f"`taskops_update status=released` with a comment explaining where you got to.")


def launch(root: Path, task: Task, *, actor: str, model: str = "") -> Launched:
    """Start a headless Claude Code on its own worktree. Returns immediately.

    A worktree that cannot be made is NOT fatal — a repository with no commits has no HEAD to branch
    from — and the worker runs in the main checkout instead. That is fine for one worker and wrong for
    several, which is why `dispatch` is the thing that decides whether to allow it.
    """
    tree = worktree_for(root, task)
    branch = branch_for(task)
    usable = make_worktree(root, tree, branch)
    log = root / WORKERS_DIR / f"{task['id']}.log"
    command = ["claude", "-p", prompt_for(task, actor),
               "--permission-mode", "acceptEdits",
               "--allowedTools", ",".join(TOOLS)]
    if model:
        command += ["--model", model]
    pid = spawn(command, cwd=tree if usable else root, log=log,
                env={"TASKOPS_ROOT": str(root), ENV_ACTOR: actor})
    return Launched(actor=actor, task=task["id"], pid=pid, tree=tree, log=log,
                    branch=branch)
