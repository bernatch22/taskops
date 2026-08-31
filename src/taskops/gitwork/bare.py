"""The board's OWN bare repository — `<root>/<board>/repo.git` (§16, "The host
becomes the remote"). This is what the smart-HTTP door serves and what the
JSON diff door reads once it exists: truth the forge does not necessarily
hold, deletable by nobody.

**Created on demand by the first WRITE-credentialed request, never by a
read.** `mounts.stores` carries the post-mortem this rule copies: a GET for a
name nobody had heard of used to leave a board directory on disk — a write
caused by a stranger's question. `repo.git` is truth, not cache, so the same
rule holds one level down: an anonymous clone of a board nobody has pushed to
answers 404 with the fact named, and the directory appears only when an
enrolled principal's push (or its ref advertisement, which git sends first)
asks for it. `http/gitpack.py` is the one caller and passes which case it is.

**It also owns the RETIREMENT of the pull mirror** (`adopt`, below): a board
whose only git is a `mirror.git` from §16's first amendment is migrated here,
once, and the mirror directory removed. That lives in this module rather than in
`mirror.py` because `mirror.py` is deleted — the thing owed to a retired
mechanism is the history it holds, and the module that keeps histories is this
one.

**Never pruned, enforced in the repo's own config.** `receive.denyDeletes`
and `receive.denyNonFastForwards` are written at creation, so the wall is
git's own, checked inside the very `git receive-pack` process that would
otherwise move the ref — there is no window between an application-level
check and the update, no pre-receive hook to install (a hook is a script on
disk that a later `git init` or a copy silently drops; config survives both),
and a client's `--force` changes nothing because the refusal is the server
process's. There is no flag that lifts either, for `board rm`'s reason (§11):
what a force would erase here is the diff of a landed card — the board's own
record. History rewriting, when it is ever needed, is the owner's deliberate
act against the host's filesystem, not a verb.
"""

from __future__ import annotations

from shutil import rmtree
from pathlib import Path

from . import run

REPO = "repo.git"

CLONE_TIMEOUT = 120.0
"""A seeding clone moves a whole history, once per board, from one local
directory to another beside it — no network in it at all, so the number is
patience against a very large repo and never a network budget."""


def at(board_dir: Path) -> Path | None:
    """The board's repo if somebody has created it — never creates one."""
    repo = board_dir / REPO
    return repo if (repo / "HEAD").is_file() else None


def ensure(board_dir: Path) -> Path:
    """Create the bare repo, refusal config included. Safe to run twice: `git
    init` on an existing repository re-reads it and moves nothing, and setting
    the same config value again is idempotent — so two racing first pushes both
    land on the same repo instead of needing a lock here."""
    repo = board_dir / REPO
    run.must(
        "init", "--bare", "--initial-branch=master", str(repo),
        why=f"cannot create the board's repository at {repo}",
    )
    run.must("config", "receive.denyDeletes", "true", cwd=repo)
    run.must("config", "receive.denyNonFastForwards", "true", cwd=repo)
    return repo


LEGACY_MIRROR = "mirror.git"
"""What §16's FIRST amendment left on disk — `<root>/<board>/mirror.git`, the
bare read-only clone of the declared forge that used to be the host's only git.
The name is kept here, in the module that replaced it, and nowhere else: the
mirror is retired, and the one thing still owed to it is the history it holds.
"""


def adopt(board_dir: Path) -> Path | None:
    """The board's repo, seeding it from a retired `mirror.git` if that is all
    this board has. Never creates an EMPTY repo — that is `ensure`'s job, and
    only a write-credentialed push may ask for it.

    §16's "On-disk" paragraph, implemented: production hosts carry a populated
    `mirror.git` today, and the reversal must not lose the history in it. So a
    board with a mirror and no `repo.git` gets one local `git clone --bare
    mirror.git repo.git` — on-disk, no network, cheap — and the mirror
    directory is then REMOVED, which is the whole point of not promoting it in
    place: `--mirror`'s fetch refspec means *make local match the forge,
    prunes included*, and a truth-holder configured to erase itself is not a
    truth-holder. `clone --bare` copies the refs and configures none of that.

    It runs on the READ path (`http/repos.py`), which is the one place that
    breaks the "a read never writes" rule on purpose and only here: this is a
    MIGRATION of a history the host already possesses, not a directory
    conjured by a stranger's question — nothing is created for a board that
    holds neither repo, so an unknown name still leaves the disk untouched. It
    happens at most once per board, ever, because the mirror is gone after it.

    A failed clone leaves the mirror alone and answers None: a migration that
    half-ran and then deleted its source would be the one unrecoverable
    outcome here.
    """
    found = at(board_dir)
    if found is not None:
        return found
    legacy = board_dir / LEGACY_MIRROR
    if not (legacy / "HEAD").is_file():
        return None
    repo = board_dir / REPO
    result = run.git("clone", "--bare", str(legacy), str(repo), timeout=CLONE_TIMEOUT)
    if not result.ok or at(board_dir) is None:
        return None
    run.must("config", "receive.denyDeletes", "true", cwd=repo)
    run.must("config", "receive.denyNonFastForwards", "true", cwd=repo)
    # `clone --bare` inherits an `origin` pointing at the mirror we are about
    # to delete — a remote that names a directory that no longer exists is a
    # lie a later `git fetch` would trip over. The outbound remote is `forge`
    # (`gitwork/onward.py`), added by the owner; nothing here needs an origin.
    run.git("remote", "remove", "origin", cwd=repo)
    rmtree(legacy, ignore_errors=True)
    return repo
