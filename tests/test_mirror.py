"""gitwork/mirror.py — the forge mirror, against a LOCAL fixture forge.

No network anywhere: the "forge" is a plain repo in tmp_path and the mirror
clones it by path, through the same `url=` override an owner's ssh remote
uses. What these pin is §16's contract — derived and disposable, one bounded
on-demand fetch, and a failure that answers within the timeout instead of
raising into a request.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskops import verbs
from taskops.mcp import boardview
from taskops._json import as_object
from taskops.store import mirroring
from taskops.gitwork import run, bare, mirror, onward
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


# ── ensure ──────────────────────────────────────────────────────────────────


def test_first_ensure_clones_a_bare_mirror(tmp_path: Path) -> None:
    forge = forge_repo(tmp_path)
    board_dir = tmp_path / "board"
    board_dir.mkdir()
    got = mirror.ensure(board_dir, None, url=str(forge))
    assert got == board_dir / "mirror.git"
    assert got.is_dir()
    # bare, and holding the forge's history
    assert run.git("rev-parse", "--is-bare-repository", cwd=got).out == "true"
    assert run.git("rev-parse", "--verify", "--quiet", "main", cwd=got).ok


def test_ensure_on_an_existing_mirror_returns_it_without_recloning(tmp_path: Path) -> None:
    """An existing mirror is returned untouched — that is how an owner's own
    remote (an ssh deploy-key address) survives every later call."""
    forge = forge_repo(tmp_path)
    board_dir = tmp_path / "board"
    board_dir.mkdir()
    first = mirror.ensure(board_dir, None, url=str(forge))
    assert first is not None
    # a second ask must not touch the remote at all: point it somewhere dead
    run.must("remote", "set-url", "origin", str(tmp_path / "gone"), cwd=first)
    again = mirror.ensure(board_dir, None, url=str(tmp_path / "gone"))
    assert again == first
    assert run.git("remote", "get-url", "origin", cwd=first).out == str(tmp_path / "gone")


def test_ensure_with_no_forge_and_no_url_is_none(tmp_path: Path) -> None:
    """The state every board is born in: no declared forge, no mirror."""
    assert mirror.ensure(tmp_path, None) is None
    assert mirror.ensure(tmp_path, {"host": "example.com", "repo": "a/b"}) is None


def test_ensure_derives_the_https_address_from_the_declared_fact(tmp_path: Path) -> None:
    """The address is spelled from core/forge.py's shape — no token, no user@."""
    assert mirror._url({"host": "github.com", "repo": "owner/name", "need": "push"}) == (
        "https://github.com/owner/name.git"
    )
    assert mirror._url(None) == ""


def test_a_failed_clone_leaves_nothing_behind(tmp_path: Path) -> None:
    board_dir = tmp_path / "board"
    board_dir.mkdir()
    assert mirror.ensure(board_dir, None, url=str(tmp_path / "nowhere")) is None
    assert not (board_dir / "mirror.git").exists()


# ── fetch ───────────────────────────────────────────────────────────────────


def test_fetch_picks_up_a_new_commit_from_the_forge(tmp_path: Path) -> None:
    forge = forge_repo(tmp_path)
    board_dir = tmp_path / "board"
    board_dir.mkdir()
    got = mirror.ensure(board_dir, None, url=str(forge))
    assert got is not None
    sha = commit(forge, "later.txt")
    # ^{commit}: bare --verify of a well-formed sha is ok even when absent
    assert not run.git("rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}", cwd=got).ok
    assert mirror.fetch(got) is True
    assert run.must("rev-parse", "main", cwd=got) == sha


def test_a_dead_remote_answers_false_within_the_timeout(tmp_path: Path) -> None:
    forge = forge_repo(tmp_path)
    board_dir = tmp_path / "board"
    board_dir.mkdir()
    got = mirror.ensure(board_dir, None, url=str(forge))
    assert got is not None
    run.must("remote", "set-url", "origin", str(tmp_path / "gone"), cwd=got)
    assert mirror.fetch(got) is False


# ── refresh_if_missing ──────────────────────────────────────────────────────


def test_a_present_ref_costs_no_fetch_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    forge = forge_repo(tmp_path)
    board_dir = tmp_path / "board"
    board_dir.mkdir()
    got = mirror.ensure(board_dir, None, url=str(forge))
    assert got is not None

    def boom(_: Path) -> bool:
        raise AssertionError("a present ref must not touch the network")

    monkeypatch.setattr(mirror, "fetch", boom)
    assert mirror.refresh_if_missing(got, "main") is True


def test_a_missing_ref_buys_exactly_one_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    forge = forge_repo(tmp_path)
    board_dir = tmp_path / "board"
    board_dir.mkdir()
    got = mirror.ensure(board_dir, None, url=str(forge))
    assert got is not None
    run.must("branch", "later", cwd=forge)

    calls: list[Path] = []
    real = mirror.fetch

    def counted(where: Path) -> bool:
        calls.append(where)
        return real(where)

    monkeypatch.setattr(mirror, "fetch", counted)
    assert mirror.refresh_if_missing(got, "later") is True
    assert calls == [got]


def test_a_ref_still_absent_after_the_fetch_is_answered_false(tmp_path: Path) -> None:
    """Stale is answered, never blocked on: 'not here' is the truth about
    this disk, and one fetch is the whole budget."""
    forge = forge_repo(tmp_path)
    board_dir = tmp_path / "board"
    board_dir.mkdir()
    got = mirror.ensure(board_dir, None, url=str(forge))
    assert got is not None
    assert mirror.refresh_if_missing(got, "never-existed") is False


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
