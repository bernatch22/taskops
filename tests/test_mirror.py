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

from taskops.gitwork import run, mirror


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
