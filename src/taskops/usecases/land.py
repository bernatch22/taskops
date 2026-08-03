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
it under LAND. From there it is a job for a `taskops-worker` sub-agent, which is the honest shape:
a conflict is two approved pieces of work disagreeing about the same lines, and deciding how they
fit is exactly the kind of small bounded task this system dispatches. Telling a person to "resolve
it by hand" is telling somebody who is not there.
"""

from __future__ import annotations

from pathlib import Path

from ..storage import LOG_FILE
from ._gitland import TRUNKS
from ._gitland import catch_trunk_up as _catch_trunk_up
from ._gitland import fetched as _fetched
from ._gitland import has_board as _has_board
from ._gitland import merged as _merged
from ._gitland import pushed as _pushed
from ._gitland import run as _run
from ._gitland import sha as _sha
from ._gitland import trunk_of as _trunk

__all__ = ["land", "Landing", "TRUNKS"]


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
    # NO blanket dirty check. There was one, and it refused every landing that has ever been
    # attempted on a real board: `taskops join` leaves `.gitignore` modified and `.mcp.json`
    # untracked in every clone it touches, forever, so "any change at all" meant "never".
    #
    # Git enforces the thing the check was reaching for, and enforces it precisely: `switch`
    # and `merge` both refuse when they would overwrite a local modification, and say which
    # file. Those refusals arrive through `_merge` like any other, so the guarantee is kept
    # and the false negative is gone.
    trunk = _trunk(root)
    if not trunk:
        return Landing(ok=False, why=f"no {' or '.join(TRUNKS)} branch in this repository")
    if not _has_board(root, trunk):
        return Landing(ok=False, trunk=trunk,
                       why=f"{LOG_FILE} is not committed on {trunk} — checking it out would "
                           f"delete this board. Commit the log on {trunk} first")
    if not _fetched(root, branch):
        return Landing(ok=False, trunk=trunk,
                       why=f"{branch} is nowhere this clone can see — the author's machine "
                           f"has not published it. `taskops publish` on their side, then "
                           f"`taskops land` this card")
    # The "already merged" shortcut lives INSIDE `_merge`, after the trunk is caught up. Asked
    # here it was answered against a LOCAL trunk and returned `ok` without pushing anything:
    # a card reported as landed whose work the shared trunk had never seen. Merged-into-my-copy
    # is not landed. Landed is "the trunk everybody pulls has it".
    return _merge(root, trunk, branch)


def _shared(root: Path, trunk: str) -> Landing:
    """A trunk that already contains the branch — landed only once the remote has it too."""
    if not _pushed(root, trunk):
        return Landing(ok=False, trunk=trunk, sha=_sha(root, trunk),
                       why=f"already merged into {trunk} here, but the remote refused it — "
                           f"`taskops land` this card again")
    return Landing(ok=True, why="", trunk=trunk, sha=_sha(root, trunk))


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
        if not _catch_trunk_up(root, trunk):
            return Landing(ok=False, trunk=trunk,
                           why=f"your {trunk} has commits the remote does not — push or "
                               f"rebase them, then `taskops land` this card")
        if _merged(root, trunk, branch):
            return _shared(root, trunk)
        if _run(root, "merge", "--no-ff", "--no-edit", branch) is None:
            _run(root, "merge", "--abort")
            return Landing(ok=False, trunk=trunk,
                           why=f"{branch} conflicts with {trunk} — spawn a `taskops-worker` "
                               f"sub-agent for this card; it resolves and merges")
        sha = _sha(root, "HEAD")
        if not _pushed(root, trunk):
            # The merge happened HERE and nowhere else, so saying `ok` would put a card in a
            # trunk nobody else can see. Reported as unlanded, which is what it is; `attention`
            # lists it under LAND and a second `taskops land` now catches the trunk up first.
            return Landing(ok=False, trunk=trunk, sha=sha,
                           why=f"merged locally but {trunk} was refused by the remote — "
                               f"somebody landed while this ran. `taskops land` this card "
                               f"again; it picks their work up first")
        return Landing(ok=True, why="", trunk=trunk, sha=sha)
    finally:
        if was != trunk:
            _run(root, "checkout", "--quiet", was)
