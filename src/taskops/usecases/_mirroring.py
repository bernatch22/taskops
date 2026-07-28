"""Bringing the local board level with a write that happened on the server.

The pull that follows a remote write carries the EVENTS, and events are enough for most of
what a board shows — but not for a claim. `engine.replay` deliberately does not materialise
leases: importing one would mean claiming a task on behalf of an agent running on another
machine, which is the opposite of what this whole feature is for. So a pull alone leaves the
winner's own board saying `ready`, and the commit guard reads that board — it refuses a commit
from an actor with no live lease HERE. The agent would have won the race and then been told it
had never claimed anything.

What is safe is narrower than what replay refuses, and this module is exactly that narrow: the
only lease written here is the one the server just GRANTED TO THIS CALLER, handed back in the
answer. It is not inferred from somebody else's event; it is the receipt for a claim this
machine made a moment ago. Everything else about other agents' claims still stays out.

The result is also applied verbatim rather than recomputed: the timestamps are the server's, so
a later status event from that same server is still newer than what is written here and replays
normally. Stamping `now()` instead would silently make the local row look newer than the server
it came from, and every subsequent pull would decline to update it.
"""

from __future__ import annotations

from pathlib import Path

from ..contracts import Claim, Task
from ._project import project

__all__ = ["mirror_claim", "mirror_update"]

_LEASE_ENDS = ("ready", "done", "cancelled")


def mirror_claim(start: Path | str, claim: Claim) -> None:
    """Record the lease the server granted, and put the card in `claimed` here too."""
    lease = claim["lease"]
    with project(start) as store:
        if store.tasks.get(lease["task"]) is None:
            return
        store.leases.release(lease["task"])
        store.leases.acquire(lease)
        store.tasks.set_status(lease["task"], "claimed", when=lease["acquired"])


def mirror_update(start: Path | str, task: Task) -> None:
    """Take the task exactly as the server returned it, and drop the lease if it ended.

    The status is copied rather than replayed because this caller has the authoritative row
    in its hands; the lease has to be dropped here because releasing one is local state and
    `replay` has no business writing it, so nothing else would ever clear it.
    """
    with project(start) as store:
        if store.tasks.get(task["id"]) is None:
            return
        store.tasks.set_status(task["id"], task["status"], when=task["updated"])
        if task["status"] in _LEASE_ENDS:
            store.leases.release(task["id"])
