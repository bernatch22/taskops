"""Landing a card's branch on the trunk — the step taskops never had.

The hole the lab made impossible to ignore: one hundred and eighteen cards closed, one hundred
and thirty-three worktrees, and `main` still on the seed commit. Every card was `done` and none
of the work was anywhere a person would look for it. Closing said "I finished"; nothing said
"this is in the trunk", and the code's own comment admitted it — *"a task can finish on a branch
somebody else lands"*. Somebody else never came.

**Approval IS the trigger.** A card reaching `done` has been read by a reviewer who is not its
author; that is exactly the moment a merge is justified, and hanging it there means nobody has
to remember. No message, no notification, no channel: the transition already happened in the
one store everybody writes to, and the merge is its consequence.

**It runs on a CLIENT, never the server.** The server has state and no checkout; git lives on
the developer's machine. Same split as `publish`: the server decides, the machine with the
repository acts.

**A conflict is WORK, not a failure.** The card closes either way — refusing over a merge would
strand finished work behind a git problem — and the outcome is recorded so `attention` can report
it under LAND. From there it is a job for a `taskops-fixer` sub-agent, which is the honest shape:
a conflict is two approved pieces of work disagreeing about the same lines, and deciding how they
fit is exactly the kind of small bounded task this system dispatches. Telling a person to "resolve
it by hand" is telling somebody who is not there.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..storage import LOG_FILE

__all__ = ["land", "Landing", "TRUNKS"]

TRUNKS = ("main", "master")
"""Where work lands, in preference order. A repository whose trunk is neither is not guessed
at: this returns `no trunk` and the card is reported unlanded rather than merged somewhere
nobody asked for."""

_TIMEOUT = 60.0


class Landing:
    """What happened, in a shape the board can record and a person can act on."""

    def __init__(self, *, ok: bool, why: str, trunk: str = "", sha: str = "") -> None:
        self.ok = ok
        self.why = why
        """Empty on success; otherwise the reason IN THE IMPERATIVE where one exists — a
        conflict a person has to resolve is not the same as a repository with no remote."""

        self.trunk = trunk
        self.sha = sha


def land(root: Path, branch: str) -> Landing:
    """Merge `branch` into the trunk and push. Never raises; never leaves a merge half-done."""
    if not branch.startswith("tk/"):
        return Landing(ok=False, why="not a task branch")
    if _run(root, "status", "--porcelain") not in ("", None):
        return Landing(ok=False, why="the working tree is dirty — commit or stash, then "
                                     "`taskops land` this card")
    trunk = _trunk(root)
    if not trunk:
        return Landing(ok=False, why=f"no {' or '.join(TRUNKS)} branch in this repository")
    if not _has_board(root, trunk):
        return Landing(ok=False, trunk=trunk,
                       why=f"{LOG_FILE} is not committed on {trunk} — checking it out would "
                           f"delete this board. Commit the log on {trunk} first")
    if _merged(root, trunk, branch):
        return Landing(ok=True, why="", trunk=trunk, sha=_sha(root, trunk))
    return _merge(root, trunk, branch)


def _merge(root: Path, trunk: str, branch: str) -> Landing:
    """Check out the trunk, merge, push, and go back where you were.

    Two ways of doing this were tried and both were worse, which is why it looks this plain.

    A worktree of its own sounds safer and is not: it advances the trunk REF while the
    developer's checkout is still standing on it, so their working tree silently falls behind
    a branch that moved underneath them. Moving somebody's branch is exactly what taskops
    forbids agents from doing with `git switch`.

    And checking out the trunk is only safe under a precondition this learned the hard way:
    `.taskops/events.jsonl` is COMMITTED, so if the log lives on the card's branch and not on
    the trunk, checking out the trunk deletes the board and the next call cannot find the
    project. `_has_board` refuses that case by name instead of discovering it mid-merge.

    The caller has already refused a dirty tree, so the checkout cannot eat anybody's work.
    `--no-ff` on purpose: a merge commit makes a card's work findable as a unit in the
    history, which is why its branch carries the card's id.
    """
    was = _run(root, "rev-parse", "--abbrev-ref", "HEAD") or trunk
    if _run(root, "checkout", "--quiet", trunk) is None:
        return Landing(ok=False, why=f"could not check out {trunk}")
    try:
        if _run(root, "merge", "--no-ff", "--no-edit", branch) is None:
            _run(root, "merge", "--abort")
            return Landing(ok=False, trunk=trunk,
                           why=f"{branch} conflicts with {trunk} — spawn a `taskops-fixer` "
                               f"sub-agent for this card; it resolves and merges")
        sha = _sha(root, "HEAD")
        _run(root, "push", "--quiet", "origin", f"{trunk}:{trunk}")
        return Landing(ok=True, why="", trunk=trunk, sha=sha)
    finally:
        if was != trunk:
            _run(root, "checkout", "--quiet", was)


def _has_board(root: Path, trunk: str) -> bool:
    """Is the event log committed on the trunk?

    The board's log is a TRACKED file, so a checkout of a trunk that lacks it deletes it — and
    then taskops cannot find its own project. Checked before the checkout, because discovering
    it afterwards means discovering it with the board already gone.
    """
    return _run(root, "cat-file", "-e", f"{trunk}:{LOG_FILE}") is not None


def _merged(root: Path, trunk: str, branch: str) -> bool:
    """Already in? Then landing is a no-op and reporting success is the honest answer."""
    listed = _run(root, "branch", "--merged", trunk, "--format=%(refname:short)")
    return listed is not None and branch in listed.splitlines()


def _trunk(root: Path) -> str:
    for name in TRUNKS:
        if _run(root, "rev-parse", "--verify", "--quiet", name) is not None:
            return name
    return ""


def _sha(root: Path, ref: str) -> str:
    return (_run(root, "rev-parse", "--short", ref) or "")[:12]


def _run(root: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(["git", *args], cwd=root, capture_output=True,
                              text=True, timeout=_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None
