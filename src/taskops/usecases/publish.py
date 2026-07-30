"""Getting a card's work off the machine that wrote it — the half a review cannot do without.

The failure, watched live and expensive: a developer's eight workers implemented eight cards on
eight branches, handed them all over, and the OTHER developer rejected seven of them with "no
hay codigo: la tarjeta paso a review sin un solo commit". Every rejection was false. The commits
existed — on branches that had never left the first machine. The reviewer was looking at its own
checkout of `main`, where those files correctly do not exist.

`reviewer: peer` turns that from friction into deadlock: the only person allowed to close a card
is the only person who cannot see it.

**So a task branch publishes itself.** Not on a schedule, not when somebody remembers — after
every commit on it, from the `post-commit` hook, because that is the moment the work exists and
the only moment anybody is holding the fact. The board already made "share it" nobody's job;
this is the same principle applied to the code the board is about.

Three fences, and each one is a way this could do harm:

- **only `tk/` branches.** taskops created them for exactly this. Pushing anything else would
  be a coordination tool taking a decision about somebody's own work.
- **never a force push**, and a rejection is left alone rather than retried differently. A
  diverged task branch is a real thing to look at, not something to overwrite.
- **never fatal.** No remote, no network, no permission: the commit already happened and the
  card is already bound. A push that fails costs the review a fetch, and `unpushed` on the
  board already says so.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

__all__ = ["publish_branch", "publish_all"]

_TIMEOUT = 20.0
"""A hook runs inside somebody's `git commit`. A push that hangs on a dead remote must not hold
a developer's terminal — losing the push is recoverable, losing the session is not."""


def publish_branch(root: Path, branch: str) -> bool:
    """Push a task branch to `origin`. True when it landed; False for every other outcome."""
    if not branch.startswith("tk/") or not _has_origin(root):
        return False
    done = _run(root, "push", "--quiet", "origin", f"{branch}:{branch}")
    if done is None:
        sys.stderr.write(f"taskops: could not publish {branch} — a reviewer on another "
                         f"machine will not see this work until it is pushed\n")
        return False
    return True


def publish_all(start: Path | str) -> list[str]:
    """Push every task branch this checkout has. Returns the ones that landed.

    The repair, and the sibling of `journal.reconcile`: a board that predates the auto-publish
    has a pile of branches that exist on exactly one laptop, and a peer reviewer cannot see any
    of them. Fifty-five of them had to be pushed by hand once, which is the definition of a
    missing verb.

    Idempotent — a branch already on the remote is a no-op push — so it is safe to run whenever
    somebody suspects work is stranded.
    """
    root = Path(start)
    listed = _run(root, "branch", "--list", "tk/*", "--format=%(refname:short)")
    if listed is None:
        return []
    return [branch for branch in listed.splitlines() if branch.strip()
            and publish_branch(root, branch.strip())]


def _has_origin(root: Path) -> bool:
    return _run(root, "remote", "get-url", "origin") is not None


def _run(root: Path, *args: str) -> str | None:
    """git, or None for any failure at all — including git not being there."""
    try:
        done = subprocess.run(["git", *args], cwd=root, capture_output=True,
                              text=True, timeout=_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None
