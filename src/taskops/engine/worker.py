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
from ._briefs import brief_for, prompt_for
from ._process import make_worktree
from .scheduler import branch_for

__all__ = ["Launched", "prepare", "worktree_for", "brief_for", "prompt_for",
           "WORKERS_DIR", "TREES_DIR"]

DROPPED_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL")
"""API credentials the worker does NOT inherit. The money rule, stated as a constant.

The `claude` CLI prefers an exported key over the logged-in subscription, so a developer who has
one in their shell was silently billing every dispatched worker per token — while the plan they
already pay for sat unused. A background agent nobody is watching must not be able to spend money
the caller did not choose to spend, and the subscription login is the default everybody expects.

`ANTHROPIC_BASE_URL` goes with them: pointing a worker at a proxy or a gateway is the same class of
surprise, decided by whoever exported a variable years ago rather than by whoever typed the command.
`taskops run --use-api-key` is the way to ask for the other mode, out loud."""

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
                 branch: str, brief: str = "", agent_type: str = "") -> None:
        self.actor = actor
        self.task = task
        self.pid = pid
        """0 when no process was started — the default, where the caller spawns a sub-agent."""

        self.tree = tree
        self.log = log
        self.branch = branch
        self.brief = brief
        """The prompt to hand a sub-agent, verbatim. Empty for a spawned worker, which got it as an
        argument instead."""

        self.agent_type = agent_type
        """Which registered specialist should run this card, or "" for the stock worker. Decided by
        `usecases.agents`, acted on by the CALLER — taskops never spawns a sub-agent itself."""


def worktree_for(root: Path, task: Task) -> Path:
    return root / TREES_DIR / task["id"]


def prepare(root: Path, task: Task, *, actor: str) -> Launched:
    """Make the worktree and write the brief. Starts NO process.

    The default half of dispatch: the caller passes `.brief` to its own sub-agent tool, so the worker
    runs on the session's existing subscription rather than opening a new billed one.
    """
    tree = worktree_for(root, task)
    make_worktree(root, tree, branch_for(task))
    return Launched(actor=actor, task=task["id"], pid=0, tree=tree, log=Path(""),
                    branch=branch_for(task), brief=brief_for(root, task, actor, tree))
