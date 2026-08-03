"""The step after a close: the card's branch meets the trunk.

Split from `update` on its budget, and the seam is the clock: everything in `update` happens
inside one locked transaction, and this deliberately happens OUTSIDE it — git is slow, and a
merge holding the write lock would block every agent on the machine for a checkout's length.
"""

from __future__ import annotations

from pathlib import Path

from ..contracts import UpdateResult
from ._project import project

__all__ = ["landed"]


def landed(start: Path | str, answer: UpdateResult, status: str, who: str) -> UpdateResult:
    """A card that just reached `done` gets its branch merged into the trunk, here.

    Approval IS the trigger: the card was read by somebody who is not its author, which is
    exactly when a merge is justified — so nobody has to remember, and no message has to
    arrive. It runs on the CLIENT because the server has state and no checkout.

    A failure never reaches the caller as an exception. The work IS done; refusing the close
    over a git conflict would strand a finished card behind a problem nobody is looking at.
    The outcome is recorded on the card instead, and `attention` reports what did not land.
    """
    if status != "done":
        return answer
    from ..engine import branch_for
    from ._project import locate
    from .land import land
    from .notelanding import note_landing

    with project(start) as store:
        commits = store.events.of_task(answer["task"]["id"], kinds=("commit",))
    if not commits:
        # Nothing to land, and saying so would be noise: a `no_code` close, a research card, a
        # decision — real work that never produced a branch. Reporting those as "not in the
        # trunk" would fill the sweep with cards nobody can act on.
        return answer
    root = locate(start)
    shas = tuple(str(e["body"].get("sha", "")) for e in commits if e["body"].get("sha"))
    # The NAME is a guess and the shas are not — see `_whichbranch`. Both, because the name is
    # still the fast path and the right thing to print when it works.
    done = land(root, branch_for(answer["task"]), shas=shas)
    # Recorded through the verb, so it reaches the BOARD. Written straight into this store it
    # reached the local cache and stopped there — on a project with a remote that is nobody's
    # board, so a card could sit unlanded for a week with every sweep reporting nothing.
    note_landing(start, task=answer["task"]["id"], ok=done.ok, why=done.why,
                 trunk=done.trunk, sha=done.sha, actor=who)
    return answer
