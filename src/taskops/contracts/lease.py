"""The lease — a claim that expires, which is what makes a crash survivable.

A boolean `assigned_to` column cannot express "this agent said it was working on
it and then its process was killed", so a board built on one accumulates tasks
nobody is doing and nobody can take. A lease has a deadline: every taskops call
the holder makes pushes it out, and silence hands the task back.

Not a filesystem lock, for the same reason: a lock file outlives the process that
took it, and cleaning one up correctly is exactly the problem a TTL already
solved.
"""

from __future__ import annotations

from typing import TypedDict

__all__ = ["Lease"]


class Lease(TypedDict):
    """Who is on a task, until when, and where they are doing it."""

    task: str
    actor: str

    session: str
    """The Claude Code session id, when the claim came from an agent.

    The join key to everything outside taskops: the transcript at
    `~/.claude/projects/<slug>/<session>.jsonl`, and the hook invocations that
    report activity. Without it, a live board can show that a task is claimed but
    not what its agent is doing right now.
    """

    branch: str
    """`tk/<id>/<slug>`, once the agent creates it. Empty until then — a claim
    happens before the branch, and the guard that binds commits to tasks needs to
    tell "no branch yet" apart from "on the wrong branch"."""

    acquired: float
    expires: float
    """When silence gives the task back. Compared against `_clock.now()`, so it
    is wall-clock and survives a restart on either side."""
