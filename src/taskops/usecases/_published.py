"""Whether the WORLD has the merge, which is the only sense of "landed" this project accepts.

Split from `land.py` on its budget, and the seam is the sentence that module keeps repeating:
merged-into-my-copy is not landed, landed is "the trunk everybody pulls has it". So nothing here
reports `ok` without a push having succeeded — a card whose merge exists on one disk stays in the
sweep under LAND, with a reason that says which half is missing.
"""

from __future__ import annotations

from pathlib import Path

from ._gitland import Landing
from ._gitland import pushed as _pushed
from ._gitland import sha as _sha

__all__ = ["published", "already_shared"]


def published(root: Path, trunk: str, sha: str, *, push: bool) -> Landing:
    """The merge is done; this is whether the WORLD has it. Split from `_merge` on the function
    budget, and the seam is the one thing this module insists on: merged-into-my-copy is not landed.

    Neither branch reports `ok` without a push, so the card stays in the sweep under LAND either
    way, with a reason that says which half is missing. `ok` on an unpublished merge would close the
    loop on work nobody else can see.
    """
    if not push:
        return Landing(ok=False, trunk=trunk, sha=sha,
                       why=f"merged into {trunk} here and NOT pushed, as asked — run the tests, "
                           f"then `taskops land` this card to publish it")
    if not _pushed(root, trunk):
        return Landing(ok=False, trunk=trunk, sha=sha,
                       why=f"merged locally but {trunk} was refused by the remote — somebody "
                           f"landed while this ran. `taskops land` this card again; it picks "
                           f"their work up first")
    return Landing(ok=True, why="", trunk=trunk, sha=sha)


def already_shared(root: Path, trunk: str) -> Landing:
    """A trunk that already contains the branch — landed only once the remote has it too."""
    if not _pushed(root, trunk):
        return Landing(ok=False, trunk=trunk, sha=_sha(root, trunk),
                       why=f"already merged into {trunk} here, but the remote refused it — "
                           f"`taskops land` this card again")
    return Landing(ok=True, why="", trunk=trunk, sha=_sha(root, trunk))
