"""Reading git, and the two conventions that bind a commit to a task.

```
branch:          tk/<task-id>/<slug>
commit trailer:  Task: tk-4f2a9c
```

Both, not either. The branch is what a human sees in `git branch` and what the guard
can check BEFORE a commit exists; the trailer is what survives a squash, a rebase and
a cherry-pick onto main, where the branch name is gone. A system with only the branch
loses every association the moment the branch is deleted — which is the normal end of
a branch's life.

Every function here degrades rather than raises. This code runs inside git hooks and
in repositories that are sometimes not repositories at all, and a coordination tool
that breaks `git commit` because it could not parse something is worse than one that
records nothing.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .._ids import TASK_PREFIX

__all__ = ["TRAILER", "task_of_branch", "task_of_message", "add_trailer",
           "current_branch", "head_sha", "commit_message", "changed_files"]

TRAILER = "Task"

_BRANCH = re.compile(rf"^tk/({re.escape(TASK_PREFIX)}[0-9a-f]+)/")
_TRAILER_LINE = re.compile(rf"^{TRAILER}:\s*({re.escape(TASK_PREFIX)}[0-9a-f]+)\s*$",
                           re.MULTILINE | re.IGNORECASE)


def task_of_branch(branch: str) -> str:
    """The task a branch belongs to, or "". Anchored, so `feat/tk-1/x` is not a match:
    a near-miss must read as unbound rather than bind to the wrong task."""
    found = _BRANCH.match(branch.strip())
    return found.group(1) if found else ""


def task_of_message(message: str) -> str:
    """The task a commit message names in its trailer, or ""."""
    found = _TRAILER_LINE.search(message)
    return found.group(1) if found else ""


def add_trailer(message: str, task_id: str) -> str:
    """Append `Task: <id>` unless the message already carries one.

    Idempotent, because the guard runs on every commit and an agent that wrote the
    trailer by hand should not get two. A trailer for a DIFFERENT task is left
    alone — the guard rejects that case rather than silently rewriting what the
    author said.
    """
    if task_of_message(message):
        return message
    body = message.rstrip("\n")
    separator = "\n\n" if "\n" not in body else "\n"
    return f"{body}{separator}{TRAILER}: {task_id}\n"


def current_branch(root: Path) -> str:
    """The checked-out branch, or "" if there is not one.

    `symbolic-ref` and NOT `rev-parse --abbrev-ref`, for two reasons that both bit:

    - On a repository with no commits yet, HEAD is unborn and `rev-parse` FAILS — so the
      branch read as "" and the guard told an agent that `tk/tk-ea4f26/…`, which it was
      standing on, "is not a task branch". Found by hand-driving the CLI in a fresh repo,
      because every test had made an initial commit first.
    - On a detached HEAD, `rev-parse --abbrev-ref` returns the literal string "HEAD", which
      is indistinguishable from a branch actually named HEAD. `symbolic-ref` fails instead,
      and failing is the honest answer: there is no branch.
    """
    return _git(root, "symbolic-ref", "--short", "HEAD")


def head_sha(root: Path) -> str:
    return _git(root, "rev-parse", "HEAD")


def commit_message(root: Path, sha: str = "HEAD") -> str:
    return _git(root, "log", "-1", "--format=%B", sha)


def changed_files(root: Path, sha: str = "HEAD") -> list[str]:
    """Paths a commit touched. Empty for the very first commit, which has no parent
    to diff against — reported as nothing rather than as a failure."""
    out = _git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", sha)
    return [line for line in out.splitlines() if line]


def _git(root: Path, *args: str) -> str:
    """One git command's stdout, or "" for any failure at all.

    Never raises, for the reason in the module docstring. `check=False` plus a
    timeout: a hook that hangs on a git subprocess hangs the developer's commit.
    """
    try:
        done = subprocess.run(["git", *args], cwd=root, capture_output=True,
                              text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""
