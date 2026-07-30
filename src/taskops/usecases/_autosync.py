"""Sync that happens because you used the board, not because you remembered to.

The three-person simulacro ran on a rule: "push after every state change". It is a good rule
and it was broken within minutes, by the person who wrote it — the boards disagreed until
somebody remembered, and remembering is exactly the job this package keeps taking away from
people. An instruction is not a mechanism.

So a project with a remote syncs AROUND the verbs themselves: a read pulls first, a local
write pushes after. `next` and `update` already execute on the server, so what this covers is
the rest — the plan somebody just wrote, the board somebody is about to read.

**Best-effort, never fatal, and that is a decision.** The alternative — refuse to show a board
when the server is down — would make the remote a single point of failure for READING local
state, which no distributed design should accept. A pull that fails leaves you exactly where
you were: looking at your last known board, which is what every offline-first tool shows. The
failure is printed to stderr rather than swallowed, because a silently stale board is the bug
this module exists to fix.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .._errors import TaskopsError
from .remote import read_remote

__all__ = ["fresh", "shared"]


def fresh(start: Path | str) -> None:
    """Pull before a read. No remote, no-op; unreachable, a warning and the local board."""
    if read_remote(start) is None:
        return
    from .pushpull import pull

    try:
        pull(start)
    except TaskopsError as err:
        _warn(f"could not pull from the remote ({err}) — showing the last board this "
              f"machine saw")


def shared(start: Path | str) -> None:
    """Push after a local write. The events are already committed locally, so a failure loses
    nothing: the next successful sync carries them, and the warning says so."""
    if read_remote(start) is None:
        return
    from .pushpull import push

    try:
        push(start)
    except TaskopsError as err:
        _warn(f"could not push to the remote ({err}) — your change is safe locally and the "
              f"next sync will carry it")


def _warn(text: str) -> None:
    # stderr, never stdout: stdout is the answer (and, on MCP, the protocol).
    sys.stderr.write(f"taskops: {text}\n")
