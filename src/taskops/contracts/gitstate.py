"""Where a task's code actually IS — on a branch, and whether anybody else can see it.

The gap this closes: a task marked `done` whose commits never left the machine is invisible to every
teammate, and the board said "done" anyway. Commits proved that work happened; this proves it is
REACHABLE. Those are different claims and only one of them was being made.
"""

from __future__ import annotations

from typing import TypedDict

__all__ = ["BranchState"]


class BranchState(TypedDict):
    """One branch's relationship to its remote."""

    branch: str
    upstream: str
    """`origin/tk/tk-4f2a9c/…`, or "" when the branch has never been pushed at all.

    Empty is the common case for a task branch and the one that matters most: it means the work
    exists on exactly one laptop.
    """

    ahead: int
    """Commits here the remote does not have. Nonzero = unpushed work."""

    behind: int
    """Commits the remote has and this branch does not — somebody else moved it."""

    pushed: bool
    """`ahead == 0` AND there is an upstream. The one boolean a card needs.

    Derived rather than left to each reader, because "pushed" from two integers and a string is a
    calculation three renderers would each get subtly wrong.
    """

    exists: bool
    """False when the branch is not in this repository at all.

    Not the same as unpushed: an agent on another machine holds a lease naming a branch this clone
    has never heard of, and a board that reported that as "0 commits, unpushed" would be describing
    a branch it cannot see as though it had looked.
    """
