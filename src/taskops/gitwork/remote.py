"""`origin` — the only thing in taskops that talks to a remote, and the switch
for everything that does.

A push here is best effort by construction: it is never a gate, never in a
commit hook, and never a board fact. `git remote get-url origin` is the ONE
question asked first — without an answer nothing is attempted and nothing is
logged, so a board with no remote behaves byte-for-byte like a taskops that
never had this module.
"""

from __future__ import annotations

from pathlib import Path

from . import run
from .._errors import TaskopsError

# A push is never a gate, so it may never cost more than a moment. 10s is long
# enough for a real push over a slow link and short enough that `done` stays a
# local operation in feel: worst case the worker waits ten seconds ONCE and the
# branch is pushed by the next lifecycle moment anyway.
PUSH_TIMEOUT = 10.0


def has_origin(path: Path) -> bool:
    """The one switch for everything that talks to a remote. No origin, no
    feature, no noise — a board without a remote behaves exactly as before."""
    return run.git("remote", "get-url", "origin", cwd=path).ok


def push(repo: Path, *branches: str, cwd: Path | None = None) -> None:
    """Best effort; whatever happened locally still happened.

    Every failure mode is swallowed on purpose — no origin, no network, a
    protected branch, a remote that hangs, git missing entirely. The caller has
    already done the thing that mattered; this only makes it visible on GitHub.
    Nothing is logged and nothing is recorded on the board: a push is not a
    board fact, and half-recorded infrastructure state is drift.
    """
    where = cwd or repo
    names = [name for name in branches if name]
    if not names or not has_origin(where):
        return
    for name in names:
        try:
            run.git("push", "origin", name, cwd=where, timeout=PUSH_TIMEOUT)
        except TaskopsError:  # timeout, or no git at all — never the caller's problem
            return
