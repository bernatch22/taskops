"""The host's relationship with the forge, against a LOCAL fixture forge.

No network anywhere: the "forge" is a plain repo in tmp_path and every remote
is a path, through the same override an owner's ssh deploy-key address uses.
Two halves, in the order the chapters happened: the pull mirror's RETIREMENT
(`gitwork/bare.py::adopt` — the history it held becomes the board's own
`repo.git`), and the OUTBOUND leg (`gitwork/onward.py` — best effort, never a
gate, every outcome legible on the board payload).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskops import verbs
from taskops.mcp import boardview
from taskops._json import as_object
from taskops.store import mirroring
from taskops.gitwork import run, bare, onward
from taskops.store.stores import Stores


def forge_repo(path: Path) -> Path:
    root = path / "forge"
    root.mkdir(parents=True)
    run.must("init", "-q", "-b", "main", str(root))
    run.must("config", "user.email", "test@example.com", cwd=root)
    run.must("config", "user.name", "Test", cwd=root)
    (root / "README.md").write_text("hello\n", encoding="utf-8")
    run.must("add", "-A", cwd=root)
    run.must("commit", "-q", "-m", "first", cwd=root)
    return root


def commit(root: Path, name: str) -> str:
    (root / name).write_text(f"{name}\n", encoding="utf-8")
    run.must("add", "-A", cwd=root)
    run.must("commit", "-q", "-m", name, cwd=root)
    return run.must("rev-parse", "HEAD", cwd=root)


# ── the pull mirror's RETIREMENT (gitwork/bare.py::adopt) ──────────────────
#
# §16's "The host becomes the remote" retires `mirror.git` and deletes
# `gitwork/mirror.py` with it. What used to be pinned here — ensure/fetch/
# refresh_if_missing, a bounded on-demand fetch, a derived-and-disposable clone
# of the forge — pinned a mechanism the chapter reversed, so it went with the
# module rather than being kept green against a source that no longer exists.
# What is owed to a mirror on disk is the HISTORY in it, and that is what these
# pin: production carries a populated `mirror.git` for taskops-v2 today, and it
# must become `repo.git` without losing a commit.


def legacy_mirror(board_dir: Path, forge: Path) -> Path:
    """A board as §16's first amendment left it: a bare mirror of the forge and
    no `repo.git`. Cloned by PATH, the same `url=` shape an owner's ssh
    deploy-key remote used, so there is no network in any of this."""
    board_dir.mkdir(parents=True, exist_ok=True)
    made = board_dir / "mirror.git"
    run.must("clone", "--mirror", str(forge), str(made))
    return made


def test_adopt_seeds_the_boards_own_repo_from_a_retired_mirror(tmp_path: Path) -> None:
    """The migration §16 promised: no history the mirror held is lost, and the
    mirror directory is gone afterwards — a truth-holder must not carry a
    `--mirror` refspec that would prune it back."""
    forge = forge_repo(tmp_path)
    run.must("branch", "tk-old", cwd=forge)
    board_dir = tmp_path / "board"
    legacy = legacy_mirror(board_dir, forge)
    head = run.must("rev-parse", "main", cwd=legacy)

    got = bare.adopt(board_dir)
    assert got == board_dir / "repo.git"
    assert run.git("rev-parse", "--is-bare-repository", cwd=got).out == "true"
    assert run.must("rev-parse", "main", cwd=got) == head
    assert run.must("rev-parse", "tk-old", cwd=got) == head  # every ref, not just HEAD
    assert not legacy.exists()


def test_the_seeded_repo_carries_the_hosts_own_refusals_and_no_origin(
    tmp_path: Path,
) -> None:
    """A seeded repo is a REMOTE, not a copy of a mirror: it refuses deletions
    and rewrites like any `bare.ensure` one, and it keeps no `origin` pointing
    at the directory the migration just deleted."""
    forge = forge_repo(tmp_path)
    board_dir = tmp_path / "board"
    legacy_mirror(board_dir, forge)
    got = bare.adopt(board_dir)
    assert got is not None
    assert run.must("config", "receive.denyDeletes", cwd=got) == "true"
    assert run.must("config", "receive.denyNonFastForwards", cwd=got) == "true"
    assert not run.git("remote", "get-url", "origin", cwd=got).ok


def test_adopt_returns_an_existing_repo_untouched_and_never_reseeds(
    tmp_path: Path,
) -> None:
    """The board's own repo OUTRANKS anything else on disk: once it exists,
    `adopt` is `at` — no clone, and a mirror left beside it is not consulted."""
    forge = forge_repo(tmp_path)
    board_dir = tmp_path / "board"
    board_dir.mkdir()
    made = bare.ensure(board_dir)
    legacy = legacy_mirror(board_dir, forge)
    assert bare.adopt(board_dir) == made
    assert not run.git("rev-parse", "--verify", "--quiet", "main", cwd=made).ok
    assert legacy.exists()  # untouched: this migration never ran


def test_adopt_creates_nothing_for_a_board_with_neither(tmp_path: Path) -> None:
    """It sits on the READ path, so the rule `mounts.stores` paid for holds one
    level down: a stranger's GET for a board nobody pushed to leaves no repo."""
    board_dir = tmp_path / "board"
    board_dir.mkdir()
    assert bare.adopt(board_dir) is None
    assert list(board_dir.iterdir()) == []


def test_a_failed_seeding_leaves_the_mirror_alone(tmp_path: Path) -> None:
    """The one unrecoverable outcome would be a half-run migration that had
    already deleted its source, so a broken clone answers None and keeps it."""
    board_dir = tmp_path / "board"
    board_dir.mkdir()
    legacy = board_dir / "mirror.git"
    legacy.mkdir()
    (legacy / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    assert bare.adopt(board_dir) is None
    assert legacy.exists()
    assert not (board_dir / "repo.git").exists()


# ── the OUTBOUND leg (gitwork/onward.py, §16 "the host becomes the remote") ──
#
# The same no-network discipline as above, pointing the other way: the "forge"
# is a bare repo in tmp_path and the outbound remote is a path. What these pin
# is the chapter's promise — a landed push is copied onward, best effort, and
# every outcome (including "the owner installed no key") is legible on the
# board payload instead of dying in a log line.


def hosted_repo(root: Path, name: str = "board") -> Path:
    """A board's own `repo.git` with one commit in it, as a push would leave it."""
    board_dir = root / name
    board_dir.mkdir(parents=True, exist_ok=True)
    repo = bare.ensure(board_dir)
    seed = forge_repo(root / f"{name}-seed")
    run.must("push", str(repo), "main:refs/heads/master", cwd=seed)
    return board_dir


def bare_forge(root: Path, name: str = "far") -> Path:
    far = root / name
    run.must("init", "--bare", "-q", "-b", "master", str(far))
    return far


def declare(stores: Stores, repo: str = "owner/name") -> None:
    verbs.call(stores, "project", "dev:berna", {"op": "forge", "repo": repo})


def test_the_outbound_leg_copies_the_whole_heads_namespace(
    tmp_path: Path, stores: Stores
) -> None:
    """A landed push reaches the declared forge, whole: the refspec is the
    namespace, not the branch this push happened to mention."""
    board_dir = hosted_repo(tmp_path)
    far = bare_forge(tmp_path)
    declare(stores)
    run.must("remote", "add", onward.REMOTE, str(far), cwd=board_dir / "repo.git")
    run.must("branch", "tk-abc123", "master", cwd=board_dir / "repo.git")

    said = onward.onward(board_dir, stores, "board")
    assert said is not None and said["ok"] is True, said
    assert said["forge"] == "github.com/owner/name"
    for ref in ("master", "tk-abc123"):
        assert run.git("rev-parse", "--verify", "--quiet", ref, cwd=far).ok, ref
    # and it is legible AS a success, on the board payload
    seen = as_object(verbs.call(stores, "board", "dev:berna", {}).get("mirror"))
    assert seen["ok"] is True and seen["detail"] == ""
    assert "up to date" in "\n".join(boardview._mirror({"mirror": seen}, seen["at"]))


def test_a_declared_forge_with_no_remote_on_the_host_fails_visibly(
    tmp_path: Path, stores: Stores
) -> None:
    """The owner declined (or has not yet made) §19.2's escalation: nothing is
    pushed, nothing is silent, and the sentence names the exact command."""
    board_dir = hosted_repo(tmp_path)
    declare(stores)

    said = onward.onward(board_dir, stores, "board")
    assert said is not None and said["ok"] is False
    assert "remote add forge git@github.com:owner/name.git" in said["detail"]

    seen = as_object(verbs.call(stores, "board", "dev:berna", {}).get("mirror"))
    assert seen["ok"] is False
    assert "FAILED" in "\n".join(boardview._mirror({"mirror": seen}, seen["at"]))


def test_an_unreachable_forge_leaves_the_hosts_history_intact(
    tmp_path: Path, stores: Stores
) -> None:
    """Best effort in the direction that matters: the host still holds every
    ref, and the reader is told what git said rather than a guess of ours."""
    board_dir = hosted_repo(tmp_path)
    declare(stores)
    repo = board_dir / "repo.git"
    run.must("remote", "add", onward.REMOTE, str(tmp_path / "not-a-repo"), cwd=repo)
    before = run.must("rev-parse", "master", cwd=repo)

    said = onward.onward(board_dir, stores, "board")
    assert said is not None and said["ok"] is False and said["detail"]
    assert run.must("rev-parse", "master", cwd=repo) == before
    assert as_object(verbs.call(stores, "board", "dev:berna", {})["mirror"])["ok"] is False


def test_no_declared_forge_means_no_attempt_at_all(
    tmp_path: Path, stores: Stores, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The state every board is born in — and not a fault: no push, no thread,
    no `mirror` key on the payload at all (`forge`'s own contract)."""
    board_dir = hosted_repo(tmp_path)

    def boom(_: Path) -> tuple[bool, str]:
        raise AssertionError("a board with no declared forge must not touch git")

    monkeypatch.setattr(onward, "push", boom)
    assert onward.onward(board_dir, stores) is None
    assert onward.after_receive(board_dir, stores) is None
    assert "mirror" not in verbs.call(stores, "board", "dev:berna", {})


def test_a_board_that_has_never_pushed_says_nothing_yet(tmp_path: Path, stores: Stores) -> None:
    """A declared forge alone is not a report: `repo.git` does not exist, so
    there is nothing to copy and nothing to claim about the copy."""
    declare(stores)
    assert onward.onward(tmp_path / "board", stores) is None
    assert "mirror" not in verbs.call(stores, "board", "dev:berna", {})


def test_an_older_observation_cannot_overwrite_a_newer_one(stores: Stores) -> None:
    """Two pushes race by construction and their threads may finish out of
    order; the report keeps the NEWEST word, so a stale failure cannot bury a
    success that happened after it."""
    mirroring.record(stores.live, "github.com/owner/name", ok=True, detail="", at=200.0)
    mirroring.record(stores.live, "github.com/owner/name", ok=False, detail="stale", at=100.0)
    seen = mirroring.last(stores.live, "github.com/owner/name")
    assert seen is not None and seen["ok"] is True
    mirroring.record(stores.live, "github.com/owner/name", ok=False, detail="fresh", at=300.0)
    later = mirroring.last(stores.live, "github.com/owner/name")
    assert later is not None and later["ok"] is False and later["detail"] == "fresh"


def test_the_report_is_keyed_on_the_forge_so_a_new_one_starts_clean(stores: Stores) -> None:
    """Re-declaring the forge must not inherit a stranger's failure."""
    mirroring.record(stores.live, "github.com/owner/one", ok=False, detail="denied", at=100.0)
    declare(stores, "owner/two")
    assert "mirror" not in verbs.call(stores, "board", "dev:berna", {})
    assert mirroring.glance(stores.live, {"host": "github.com", "repo": "owner/one"}) == {}
