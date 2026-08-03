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
from ._gitland import TRUNKS, Landing
from ._gitland import catch_trunk_up as _catch_trunk_up
from ._gitland import fetched as _fetched
from ._gitland import has_board as _has_board
from ._gitland import merged as _merged
from ._gitland import run as _run
from ._gitland import sha as _sha
from ._gitland import trunk_of as _trunk
from ._published import already_shared as _shared
from ._published import published as _publish
from ._whichbranch import actual as _actual

__all__ = ["land", "Landing", "TRUNKS"]


def land(root: Path, branch: str, *, shas: tuple[str, ...] = (), push: bool = True) -> Landing:
    """Merge the card's branch into the trunk and push. Never raises; never half-merges.

    `branch` is a GUESS — the name `branch_for` computes — and `shas` are the card's commits, which
    are not. When the guess is not here, the commits say which branch is: see `_whichbranch`.

    `push=False` merges and stops, and it does NOT report the card landed — see `_merge`. It exists
    because landing is the step that most wants a green suite BEFORE anything is published, and with
    the push welded in that was impossible: a worker told "do not push until the tests pass" landed
    three cards and all three went to origin inside the merge.
    """
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
        found = _actual(root, branch, shas)
        if found.why:
            return Landing(ok=False, trunk=trunk, why=found.why)
        branch = found.branch
    # The "already merged" shortcut lives INSIDE `_merge`, after the trunk is caught up. Asked
    # here it was answered against a LOCAL trunk and returned `ok` without pushing anything:
    # a card reported as landed whose work the shared trunk had never seen. Merged-into-my-copy
    # is not landed. Landed is "the trunk everybody pulls has it".
    return _merge(root, trunk, branch, push=push)


def _merge(root: Path, trunk: str, branch: str, *, push: bool = True) -> Landing:
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
        return _publish(root, trunk, _sha(root, "HEAD"), push=push)
    finally:
        if was != trunk:
            _run(root, "checkout", "--quiet", was)
