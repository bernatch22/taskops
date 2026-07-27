"""Reading how far a branch is from its remote. Cheap, batched, and never raising.

The question a board has to answer is "can anybody else see this work yet", and git already knows.
One `for-each-ref` returns every local branch with its upstream and its ahead/behind counts, which
is why this is one subprocess for a whole board rather than one per card.

Same rule as the rest of `gitio`: every function degrades to a useless-but-honest answer instead of
raising. This runs inside a board refresh and inside hooks, and a coordination tool that breaks
because a branch was deleted mid-read is worse than one that reports `exists: False`.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ..contracts import BranchState

__all__ = ["branch_states", "branch_state", "unknown"]

_TRACK = re.compile(r"ahead (\d+)|behind (\d+)")
_SEP = "\x1f"          # unit separator: cannot appear in a ref name, unlike anything printable


def unknown(branch: str) -> BranchState:
    """The answer for a branch this repository does not have.

    Its own constructor because the honest empty value is easy to get wrong: `exists=False` with
    `pushed=False` reads as "unpushed work", and the truth is "no idea, not here".
    """
    return BranchState(branch=branch, upstream="", ahead=0, behind=0, pushed=False,
                       exists=False)


def branch_states(root: Path) -> dict[str, BranchState]:
    """Every local branch, keyed by name. ONE subprocess for a whole board."""
    fields = f"%(refname:short){_SEP}%(upstream:short){_SEP}%(upstream:track)"
    out = _git(root, "for-each-ref", f"--format={fields}", "refs/heads")
    states: dict[str, BranchState] = {}
    for line in out.splitlines():
        parts = line.split(_SEP)
        if len(parts) != 3 or not parts[0]:
            continue
        states[parts[0]] = _state(parts[0], parts[1], parts[2])
    return states


def branch_state(root: Path, branch: str) -> BranchState:
    """One branch. Convenience over `branch_states` for a single-task read."""
    if not branch:
        return unknown(branch)
    return branch_states(root).get(branch, unknown(branch))


def _state(branch: str, upstream: str, track: str) -> BranchState:
    """`[ahead 3, behind 1]` -> the numbers.

    A branch with no upstream reports `ahead=0`, and that is NOT "nothing to push": git has nothing
    to compare against, so the count is unknown while the work is definitely unpushed. `pushed`
    therefore requires an upstream, which is what keeps a never-pushed branch from reading as clean.
    """
    ahead, behind = 0, 0
    for match in _TRACK.finditer(track):
        if match.group(1):
            ahead = int(match.group(1))
        elif match.group(2):
            behind = int(match.group(2))
    return BranchState(branch=branch, upstream=upstream, ahead=ahead, behind=behind,
                       pushed=bool(upstream) and ahead == 0, exists=True)


def _git(root: Path, *args: str) -> str:
    """One git command's stdout, or "" for any failure.

    Never raises, for the reason in the module docstring. `check=False` plus a timeout, because a
    board refresh must not hang on a repository whose index is locked by somebody's rebase.
    """
    try:
        done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                              timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""
