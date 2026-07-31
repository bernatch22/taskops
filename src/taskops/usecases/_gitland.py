"""The git a landing runs — the half of `land` that is commands rather than judgement.

Split on the line budget, and the seam is the usual one: `land` decides whether a merge should
happen and what its failure MEANS to a board; everything here shells out and reports what git
said. The invariant that forced the split was right — the two halves are read for different
reasons, and only this one has to be read with `git help merge` open.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..storage import LOG_FILE

__all__ = ["fetched", "has_board", "merged", "run", "sha", "trunk_of", "TRUNKS", "TIMEOUT"]

TRUNKS = ("main", "master")
"""Where work lands, in preference order. A repository whose trunk is neither is not guessed
at: landing reports `no trunk` and the card is left unlanded rather than merged somewhere
nobody asked for."""

TIMEOUT = 60.0


def fetched(root: Path, branch: str) -> bool:
    """Make sure the branch exists HERE, pulling it from the remote if it does not.

    The whole point of peer review is that the closer is not the author, so the branch was
    written on another machine and this clone has never seen it — which is exactly what
    happened the first time a real reviewer closed a real card. Branches are published on
    every commit, so the remote has it; nothing was fetching it.

    A repository with no remote answers from what it already has, which is the only thing it
    could ever have meant.
    """
    if run(root, "rev-parse", "--verify", "--quiet", branch) is not None:
        return True
    if run(root, "remote") in ("", None):
        return False
    run(root, "fetch", "--quiet", "origin", f"{branch}:{branch}")
    return run(root, "rev-parse", "--verify", "--quiet", branch) is not None


def has_board(root: Path, trunk: str) -> bool:
    """Would checking out the trunk lose this board's log?

    The question is about THIS checkout, not about the trunk. When the log is a tracked file,
    a trunk that lacks it deletes it on checkout and taskops can no longer find its own
    project — so that case is refused before the checkout rather than discovered after it.

    When the log is NOT tracked here, there is nothing to lose and the rule does not apply.
    That is every project with a remote: the log lives on the server and `.taskops/` is a
    gitignored cache. Asking the old question there refused every landing on the board — the
    trunk of course did not carry a file that is deliberately not in git.
    """
    if run(root, "ls-files", "--error-unmatch", LOG_FILE) is None:
        return True
    return run(root, "cat-file", "-e", f"{trunk}:{LOG_FILE}") is not None


def merged(root: Path, trunk: str, branch: str) -> bool:
    """Already in? Then landing is a no-op and reporting success is the honest answer."""
    listed = run(root, "branch", "--merged", trunk, "--format=%(refname:short)")
    return listed is not None and branch in listed.splitlines()


def trunk_of(root: Path) -> str:
    for name in TRUNKS:
        if run(root, "rev-parse", "--verify", "--quiet", name) is not None:
            return name
    return ""


def sha(root: Path, ref: str) -> str:
    return (run(root, "rev-parse", "--short", ref) or "")[:12]


def run(root: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(["git", *args], cwd=root, capture_output=True,
                              text=True, timeout=TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None
