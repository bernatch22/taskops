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

from pathlib import Path

from . import run

REPO = "repo.git"


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
