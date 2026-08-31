"""The outbound leg — `repo.git` → the declared forge, after a push lands.

§16 ("The host becomes the remote") inverted the forge relationship: the host
holds the history and GitHub is a full COPY of it. So a push that lands here
is pushed onward, and `mirror.py`'s pull direction retires — one direction on
each leg (worktree → host, host → forge), which is what keeps §11's
replication ban intact through the reversal.

**Best effort, and never a gate — in outcome AND in time.** The client's push
has already landed; nothing here may fail it, revert it, or make it wait. The
budget is `remote.py::PUSH_TIMEOUT`, reused rather than re-decided, because it
is the same question with the same answer ("a push is never a gate, so it may
never cost more than a moment"), and the work runs on a BACKGROUND thread
started after the response is on the wire: inline, a forge that hangs would
hold the receive door's thread and delay the very `git push` that already
succeeded — the client would experience the mirror as a ten-second gate, which
is the one thing it must never be.

**Two pushes racing is normal and needs no lock.** The refspec is the whole
`refs/heads/*`, so a later push SUBSUMES an earlier one: whichever thread runs
last leaves the forge holding everything both of them had, and an interleaved
pair does the same work twice at worst. What does need care is the REPORT,
which is why `store/mirroring.py` guards its upsert by timestamp — threads may
finish out of order and an older failure must not overwrite a newer success.

**Failure is visible, never swallowed.** Every outcome is recorded as the
board's `mirror` fact (`store/mirroring.py` argues that channel: the board
payload, not a log line), including the one an owner is most likely to hit —
no credential on the host. Nothing here raises into the door.

**The credential is the OWNER's, and this module knows nothing about it**
(§19.2, the escalation). The address is a remote named `forge` inside
`repo.git`, configured by the owner by hand:

    git -C <root>/<board>/repo.git remote add forge git@github.com:owner/name.git

backed by a WRITE deploy key in the host user's ssh config. It is deliberately
NOT derived from the declared fact the way `mirror.py::_url` derived its
anonymous https address: an https push would need a token, and a token is what
§11 bans. A forge declared with no remote configured is the "no key" case and
reads as a failure naming that exact command — an owner who declines the
escalation is told so on every board read, and the read side stays whole.

**Fast-forward only, never a force, never a prune.** `--mirror` is the refspec
that would have made this one line, and it DELETES on the far side; a force
would rewrite there. The host demands neither of itself (`bare.py` writes
`receive.denyDeletes` into its own config) and does not do to the forge what it
refuses for itself. A branch pruned on GitHub simply comes back on the next
push, which is the whole point of the chapter.
"""

from __future__ import annotations

from typing import Any
from pathlib import Path
from threading import Thread

from . import run, bare, remote
from .. import _clock
from ..core import forge as forges
from ..store import mirroring
from ..verbs import project
from .._errors import TaskopsError
from ..store.stores import Stores

__all__ = ["REMOTE", "REFSPEC", "configured", "push", "onward", "after_receive"]

REMOTE = "forge"
"""The remote name inside `repo.git`. `origin` is deliberately not reused: on
the host, `repo.git` has no origin — it was created empty by a client's push
(`bare.py`) — and a name that says what the far side IS cannot be confused
with the worktree's own remote by an owner reading `git remote -v`."""

REFSPEC = "refs/heads/*:refs/heads/*"
"""Both sides spelled out, for `remote.py::push`'s measured reason (a
one-sided refspec is resolved through `push.default`), and the whole namespace
because the host is the source: a card branch that landed here belongs on the
forge whether or not this particular push mentioned it. Heads only — tags are
not what this chapter is about, and a tag is a publication."""

NO_REMOTE = (
    "nothing was pushed onward: board {board!r} declares the forge {forge} and "
    "this host has no remote named {remote!r} in its repo.git. That credential is "
    "the owner's explicit act (ARCHITECTURE §19.2) — mint a WRITE deploy key for "
    "the repo, install it for the host user, then run: git -C {repo} remote add "
    "{remote} git@{host}:{slug}.git"
)
"""The failure an owner is most likely to meet, and the only one whose words are
ours rather than git's: git cannot say "you have not decided yet". It leads with
the consequence and ends with the exact command, because it is read on a board
payload where the tail is what a length cap would cut."""


def configured(repo: Path) -> str:
    """The owner's outbound address, or "" — the one question, asked once."""
    result = run.git("remote", "get-url", REMOTE, cwd=repo)
    return result.out if result.ok else ""


def push(repo: Path) -> tuple[bool, str]:
    """`(ok, detail)` — never raises, whatever the network or git does.

    `run.git` RAISES on a timeout (right for a worker, wrong for a leg nobody
    is waiting on), so the catch is part of the contract exactly as it is in
    `mirror.py`. `detail` is git's own words, because a mirror failure is read
    by the owner who has to fix it: "Permission denied (publickey)" IS the
    instruction, and a sentence of ours in its place would be a guess.
    """
    try:
        result = run.git("push", REMOTE, REFSPEC, cwd=repo, timeout=remote.PUSH_TIMEOUT)
    except TaskopsError as err:  # timeout, or no git at all
        return False, str(err)
    if result.ok:
        return True, ""
    said = (result.err or result.out).strip()
    return False, said or f"git push exited {result.code} and said nothing"


def onward(board_dir: Path, stores: Stores, board: str = "") -> dict[str, Any] | None:
    """Push onward and record what happened. None means nothing was attempted.

    A board with NO declared forge returns None before touching git: no
    mirroring, no attempt, no error — §16's "not a fault", and the state every
    board is born in. No `repo.git` is the same answer: there is nothing to
    copy yet.
    """
    fact = project.forge(stores)
    if fact is None:
        return None
    repo = bare.at(board_dir)
    if repo is None:
        return None
    where = configured(repo)
    if not where:
        ok, detail = False, NO_REMOTE.format(
            board=board or board_dir.name,
            forge=forges.label(fact),
            remote=REMOTE,
            repo=repo,
            host=fact["host"],
            slug=fact["repo"],
        )
    else:
        ok, detail = push(repo)
    at = _clock.now()
    try:
        mirroring.record(stores.live, forges.label(fact), ok=ok, detail=detail, at=at)
    except TaskopsError:  # a live store this thread cannot write is not the push's problem
        return None
    return {"forge": forges.label(fact), "ok": ok, "at": at, "detail": detail}


def after_receive(board_dir: Path, stores: Stores, board: str = "") -> Thread | None:
    """Start the outbound leg for a push that just landed, or return None.

    The thread is a daemon: a host shutting down must not wait on a forge, and
    the next push repeats the whole refspec anyway, so an interrupted mirror
    costs nothing but a report that stays honest about the last one that ran.
    The forge fact is asked HERE too, so a board without one starts no thread
    at all — "no attempt" is a promise about the process table as well.
    """
    if project.forge(stores) is None:
        return None
    thread = Thread(
        target=onward, args=(board_dir, stores, board), name="taskops-mirror", daemon=True
    )
    thread.start()
    return thread
