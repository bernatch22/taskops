"""WHICH branch a card's work is on — a different question from how to merge it.

`land.py` knows the git dance: check out the trunk, catch it up, merge, push, go back. This knows
the one thing that dance cannot assume, and the module budget is what separated them: the branch
NAME is computed in three places (`next` prints one, the commit guard checks one, `land` looks for
one), so it is not evidence. The card's commits are.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from ._gitland import carrying

__all__ = ["actual"]


class Actual(NamedTuple):
    branch: str
    why: str


def actual(root: Path, guess: str, shas: tuple[str, ...]) -> Actual:
    """The branch this card's COMMITS are on, when the computed name is not here.

    The old refusal said the author had not published it and told them to run `taskops publish`.
    Measured on a real board, the branch WAS published: `branch_for` answered
    `…-toggle-toll-of-a-c` and the branch was `…-toggle-toll-of-a`, one character apart, because
    the clone that created it computes the slug differently. So the message accused another
    developer of something it had no way to know, and sent them to run a command that had already
    been run.

    Now the commits decide, and the refusals say what was looked for. Several matches is refused
    rather than guessed: two branches carrying one card's commits is a fact about the repository
    that a merge should not resolve on its own.
    """
    if not shas:
        return Actual("", f"{guess} is not in this clone, and this card records no commit to "
                           f"find it by — nothing to land")
    carries = carrying(root, list(shas))
    if len(carries) == 1:
        return Actual(carries[0], "")
    listed = ", ".join(carries) if carries else "none"
    seen = ", ".join(shas)
    return Actual("", f"{guess} is not in this clone, and the commits of this card ({seen}) are "
                       f"on: {listed}. If that is empty, whoever wrote them has not published "
                       f"the branch — `taskops publish` on their machine. If it names several, "
                       f"say which with `git branch` and land it by hand")
