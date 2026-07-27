"""Running a detached process in a git worktree. The mechanics, not the policy.

Split from `worker` by what a reader needs to know: that module decides WHAT to launch and what to
tell it, this one knows how to get a process running somewhere it cannot damage anybody else.

Two decisions carry it:

**A worktree per worker.** Parallel agents editing one working tree overwrite each other, and no
amount of lease bookkeeping fixes that — a lease coordinates who owns a TASK, not whose bytes are on
disk. `git worktree` gives each worker its own directory on its own branch, and they merge through
git like any two developers.

**Detached, output to a file.** A dispatched worker outlives the call that launched it, so it is
started in its own session and its stdout goes to a file. Not a pipe: nobody is reading it, and a
full pipe buffer deadlocks the child.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

__all__ = ["make_worktree", "spawn"]


def make_worktree(root: Path, tree: Path, branch: str) -> bool:
    """Create the worktree; True if it is usable. Reuses the branch when it already exists.

    Two `git worktree add` forms, because the branch may or may not exist yet: `-b` creates it, and
    plain `add` attaches to one an earlier dispatch already made. Trying `-b` on an existing branch
    fails, which would strand a re-dispatched task in the main checkout beside its siblings.
    """
    tree.parent.mkdir(parents=True, exist_ok=True)
    if tree.is_dir():
        return True
    if _git(root, "worktree", "add", "-b", branch, str(tree)):
        return True
    return _git(root, "worktree", "add", str(tree), branch)


def spawn(command: list[str], *, cwd: Path, log: Path, env: dict[str, str]) -> int:
    """Start a detached process, output to `log`. Returns its pid, or 0 if it could not start.

    `start_new_session` puts it in its own process group, so a ctrl-C in the terminal that ran
    dispatch does not kill the workers it launched — they are meant to outlive it.

    The environment is INHERITED and then extended, because a worker needs the developer's PATH and
    credentials to run `claude` at all.
    """
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        with log.open("wb") as sink:
            process = subprocess.Popen(command, cwd=cwd, stdout=sink,
                                       stderr=subprocess.STDOUT,
                                       stdin=subprocess.DEVNULL,
                                       start_new_session=True,
                                       env={**os.environ, **env})
        return process.pid
    except OSError:
        # 0 rather than raising: dispatching five workers where one fails to start should report
        # four running and one that did not, never lose the four.
        return 0


def _git(root: Path, *args: str) -> bool:
    """True if the command succeeded. Never raises, like everything that shells out to git here."""
    try:
        done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                              timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0
