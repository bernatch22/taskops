"""What a worker is TOLD. Two audiences, two texts, and the difference matters.

A sub-agent of the current session and a spawned process are not the same reader:

- A **sub-agent** shares the parent's working directory, so it has to be told which worktree is its
  own and told never to switch branches. Nothing else stops it editing `main` — and if two of them
  did, they would overwrite each other in the one place no lease can protect.
- A **process** starts in its worktree already, with `$TASKOPS_ROOT` pointing at the shared board, so
  its brief can be short.

Both end the same way, and that sentence is the most important one in either: an agent that guesses
when the spec is wrong produces a commit somebody has to read and undo. Told to release instead, it
hands back everything it learned.
"""

from __future__ import annotations

from pathlib import Path

from ..contracts import Task
from .scheduler import branch_for

__all__ = ["prompt_for", "brief_for"]


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


def brief_for(root: Path, task: Task, actor: str, tree: Path) -> str:
    """The prompt for a SUB-AGENT of the current session. What `dispatch` hands back.

    Different from `prompt_for` in the two ways that matter for a sub-agent rather than a process:

    - It names the WORKTREE PATH and says to work there. A sub-agent shares the parent's working
      directory, so nothing stops it editing `main` unless told otherwise — and if two of them did,
      they would overwrite each other in the one place no lease can protect.
    - It says never to `git switch`. The worktree is ALREADY on the card's branch; switching in the
      shared checkout would move the branch under every other agent at once, which is the failure
      that makes people conclude parallel agents cannot work on separate branches.

    `$TASKOPS_ROOT` is not needed here: a sub-agent inherits the session's environment and the
    project resolves by walking up from the worktree, which is inside the repository.
    """
    return (
        f"You are taskops worker `{actor}` on card {task['id']}: {task['title']}\n\n"
        f"YOUR WORKTREE: {tree}\n"
        f"Work ONLY inside that directory. It is already checked out on branch "
        f"`{branch_for(task)}` — never run `git switch`/`git checkout <branch>`, because other "
        f"workers share this repository and switching would move their branch too.\n\n"
        f"Steps:\n"
        f"1. `taskops_next repo_path={root} task={task['id']} actor={actor}` — claims it and "
        f"prints the full spec plus a warning if another worker touches your files.\n"
        f"2. Do the work in {tree}. Read .taskops/GUIDE.md if anything is unclear.\n"
        f"3. Commit inside your worktree: `git -C {tree} add -A && git -C {tree} commit -m '...' "
        f"-m 'Task: {task['id']}'`. The trailer is what binds the commit to the card.\n"
        f"4. `taskops_update repo_path={root} task={task['id']} actor={actor} status=done "
        f"comment='<what you did>'`.\n\n"
        f"If you get stuck or the spec is wrong, do NOT guess: "
        f"`taskops_update repo_path={root} task={task['id']} actor={actor} status=released "
        f"comment='<where you got to and what blocked you>'`. That returns the card with everything "
        f"you learned, which is worth far more than a wrong commit."
    )


