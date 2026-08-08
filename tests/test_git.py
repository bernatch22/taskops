"""gitwork/ — against real repositories in tmp_path. No mocks: git is the point."""

from __future__ import annotations

from typing import Any
from pathlib import Path

import pytest

from taskops import board
from taskops._errors import Refused, NotFound, TaskopsError
from taskops.gitwork import run, bind, trees, remote, install, trailer


def repo(path: Path, name: str = "work") -> Path:
    root = path / name
    root.mkdir(parents=True)
    run.must("init", "-q", "-b", "main", str(root))
    run.must("config", "user.email", "test@example.com", cwd=root)
    run.must("config", "user.name", "Test", cwd=root)
    (root / "README.md").write_text("hello\n", encoding="utf-8")
    run.must("add", "-A", cwd=root)
    run.must("commit", "-q", "-m", "first", cwd=root)
    return root


# ── run ─────────────────────────────────────────────────────────────────────


def test_git_errors_come_back_with_what_git_actually_said(tmp_path: Path) -> None:
    """v1 swallowed stderr and turned a refused push into 'somebody landed'."""
    root = repo(tmp_path)
    result = run.git("checkout", "nope", cwd=root)
    assert not result.ok and "nope" in result.err
    with pytest.raises(Refused, match="git said"):
        run.must("checkout", "nope", cwd=root, why="cannot switch")


# ── the trailer ─────────────────────────────────────────────────────────────


def test_the_trailer_goes_after_a_blank_line(tmp_path: Path) -> None:
    """Flush against the body, git does not parse it as a trailer at all."""
    out = trailer.stamped("feat: parser\n", "tk-b22222")
    assert out == "feat: parser\n\nTask: tk-b22222\n"
    assert trailer.card_in(out) == "tk-b22222"


def test_stamping_twice_changes_nothing(tmp_path: Path) -> None:
    once = trailer.stamped("feat: parser", "tk-b22222")
    assert trailer.stamped(once, "tk-b22222") == once


def test_a_branch_without_a_card_is_left_alone(tmp_path: Path) -> None:
    assert trailer.card_of("ms/mvp") == "" and trailer.card_of("main") == ""
    assert trailer.stamped("chore: tidy", "") == "chore: tidy"


def test_the_installed_hook_stamps_a_real_commit(tmp_path: Path) -> None:
    import sys

    root = repo(tmp_path)
    install.install_hooks(root, sys.executable)
    run.must("checkout", "-q", "-b", "tk-b22222", cwd=root)
    (root / "parser.py").write_text("x = 1\n", encoding="utf-8")
    run.must("add", "-A", cwd=root)
    run.must("commit", "-q", "-m", "feat: parser", cwd=root)
    body = run.must("show", "-s", "--format=%B", cwd=root)
    assert "Task: tk-b22222" in body
    assert run.must("show", "-s", "--format=%(trailers:key=Task,valueonly)", cwd=root).strip() == (
        "tk-b22222"
    )


# ── worktrees ───────────────────────────────────────────────────────────────


def test_two_cards_of_two_milestones_coexist(tmp_path: Path) -> None:
    """The whole point: branches are not switched, they are inhabited."""
    root = repo(tmp_path)
    trees.ensure_milestone(root, "ms/mvp")
    trees.ensure_milestone(root, "ms/reports")
    first = trees.ensure_card(root, "tk-a11111", "tk-a11111", "ms/mvp")
    second = trees.ensure_card(root, "tk-x99999", "tk-x99999", "ms/reports")

    assert run.branch_at(root) == "main"  # the shared checkout never moved
    assert run.branch_at(first) == "tk-a11111"
    assert run.branch_at(second) == "tk-x99999"
    assert run.branch_at(trees.integration_tree(root, "ms/mvp")) == "ms/mvp"


def test_git_itself_refuses_the_same_branch_in_two_places(tmp_path: Path) -> None:
    root = repo(tmp_path)
    trees.ensure_card(root, "tk-a11111", "tk-a11111", "ms/mvp")
    result = run.git("worktree", "add", str(tmp_path / "elsewhere"), "tk-a11111", cwd=root)
    assert not result.ok and "already used" in result.err.lower()


def test_reopening_an_existing_worktree_is_a_no_op(tmp_path: Path) -> None:
    root = repo(tmp_path)
    first = trees.ensure_card(root, "tk-a11111", "tk-a11111", "ms/mvp")
    assert trees.ensure_card(root, "tk-a11111", "tk-a11111", "ms/mvp") == first


def test_merge_integrates_into_the_milestone_branch(tmp_path: Path) -> None:
    root = repo(tmp_path)
    tree = trees.ensure_card(root, "tk-a11111", "tk-a11111", "ms/mvp")
    (tree / "models.py").write_text("class Invoice: ...\n", encoding="utf-8")
    run.must("add", "-A", cwd=tree)
    run.must("commit", "-q", "-m", "feat: model", cwd=tree)

    sha = trees.merge_card(root, "ms/mvp", "tk-a11111", "tk-a11111")
    integration = trees.integration_tree(root, "ms/mvp")
    assert (integration / "models.py").exists()
    assert run.must("rev-parse", "HEAD", cwd=integration) == sha
    assert run.must("rev-parse", "main", cwd=root) != sha  # main is the human's


def test_a_conflict_aborts_clean_and_names_the_files(tmp_path: Path) -> None:
    root = repo(tmp_path)
    integration = trees.ensure_milestone(root, "ms/mvp")
    (integration / "models.py").write_text("theirs\n", encoding="utf-8")
    run.must("add", "-A", cwd=integration)
    run.must("commit", "-q", "-m", "theirs", cwd=integration)
    before = run.must("rev-parse", "HEAD", cwd=integration)

    tree = trees.ensure_card(root, "tk-d44444", "tk-d44444", "ms/mvp")
    run.must("reset", "-q", "--hard", "main", cwd=tree)
    (tree / "models.py").write_text("mine\n", encoding="utf-8")
    run.must("add", "-A", cwd=tree)
    run.must("commit", "-q", "-m", "mine", cwd=tree)

    with pytest.raises(Refused) as caught:
        trees.merge_card(root, "ms/mvp", "tk-d44444", "tk-d44444")
    assert "models.py" in str(caught.value)
    assert run.must("rev-parse", "HEAD", cwd=integration) == before  # untouched
    assert not (integration / ".git" / "MERGE_HEAD").exists()

    # The way out it names must be one that WORKS. This used to say "re-dispatch
    # it: its worktree is re-cut from ms/*" — and a worktree is pinned to its
    # branch for life, so `ensure_card` reuses the directory and re-cutting
    # never happens. A worker following that line verbatim re-ran the identical
    # conflict. (This assertion replaced one that pinned the wrong instruction.)
    assert f"cd {trees.card_tree(root, 'tk-d44444')} && git merge ms/mvp" in str(caught.value)
    assert trees.ensure_card(root, "tk-d44444", "tk-d44444", "ms/mvp") == tree  # reused, not re-cut

    resolved = trees.card_tree(root, "tk-d44444")
    run.git("merge", "ms/mvp", cwd=resolved)  # conflicts, as the message expects
    (resolved / "models.py").write_text("both\n", encoding="utf-8")
    run.must("add", "-A", cwd=resolved)
    run.must("commit", "-q", "--no-verify", "-m", "resolve", cwd=resolved)
    assert trees.merge_card(root, "ms/mvp", "tk-d44444", "tk-d44444")  # now it lands


def test_tidy_only_removes_what_is_already_in_the_trunk(tmp_path: Path) -> None:
    root = repo(tmp_path)
    kept = trees.ensure_card(root, "tk-b22222", "tk-b22222", "ms/mvp")
    (kept / "parser.py").write_text("x = 1\n", encoding="utf-8")
    run.must("add", "-A", cwd=kept)
    run.must("commit", "-q", "-m", "feat: parser", cwd=kept)
    merged = trees.ensure_card(root, "tk-a11111", "tk-a11111", "ms/mvp")

    removed = trees.tidy(root, trunk="main")
    assert any("tk-a11111" in line for line in removed)  # nothing of its own yet
    assert not merged.exists() and kept.exists()  # unmerged work is never deleted


# ── pushing ─────────────────────────────────────────────────────────────────


def origin_for(root: Path, path: Path) -> Path:
    """A bare repo wired up as `origin`."""
    run.must("init", "-q", "--bare", str(path))
    run.must("remote", "add", "origin", str(path), cwd=root)
    return path


def test_a_card_branch_reaches_origin_when_there_is_one(tmp_path: Path) -> None:
    root = repo(tmp_path)
    bare = origin_for(root, tmp_path / "origin.git")
    tree = trees.ensure_card(root, "tk-a11111", "tk-a11111", "")
    (tree / "models.py").write_text("class Invoice: ...\n", encoding="utf-8")
    run.must("add", "-A", cwd=tree)
    run.must("commit", "-q", "-m", "feat: model", cwd=tree)

    remote.push(root, "tk-a11111")
    assert run.must("rev-parse", "tk-a11111", cwd=bare) == run.must(
        "rev-parse", "HEAD", cwd=tree
    )


def test_with_no_origin_no_push_is_even_attempted(tmp_path: Path) -> None:
    """Byte-for-byte today's behaviour: the switch is `git remote get-url
    origin`, and without one git is never asked to push at all — not asked and
    allowed to fail, which would be a slow no-op and a line of noise."""
    root = repo(tmp_path)
    ran: list[tuple[str, ...]] = []
    real = run.git

    def spy(*args: str, **kwargs: Any) -> Any:
        ran.append(args)
        return real(*args, **kwargs)

    remote.run.git = spy  # type: ignore[assignment]
    try:
        remote.push(root, "main")
    finally:
        remote.run.git = real  # type: ignore[assignment]
    assert not any(args[0] == "push" for args in ran)


def test_a_remote_that_hangs_does_not_reach_the_caller(tmp_path: Path) -> None:
    """`run.git` RAISES on a timeout — it is the one failure that is not an exit
    code — and a `done` that raised because origin was slow would be a push used
    as a gate. Ten seconds is the ceiling, and past it nothing happened."""
    root = repo(tmp_path)
    origin_for(root, tmp_path / "origin.git")
    real = run.git

    def hang(*args: str, **kwargs: Any) -> Any:
        if args[0] == "push":
            raise TaskopsError("git push took longer than 10.0s")
        return real(*args, **kwargs)

    remote.run.git = hang  # type: ignore[assignment]
    try:
        remote.push(root, "main")  # returns, says nothing, raises nothing
    finally:
        remote.run.git = real  # type: ignore[assignment]
    assert remote.PUSH_TIMEOUT <= 30.0  # a lifecycle moment may not wait on a remote


def test_a_push_that_fails_changes_nothing_about_the_merge(tmp_path: Path) -> None:
    """origin exists but is unreachable — the integration still happened."""
    root = repo(tmp_path)
    run.must("remote", "add", "origin", str(tmp_path / "nowhere.git"), cwd=root)
    tree = trees.ensure_card(root, "tk-a11111", "tk-a11111", "ms/mvp")
    (tree / "models.py").write_text("class Invoice: ...\n", encoding="utf-8")
    run.must("add", "-A", cwd=tree)
    run.must("commit", "-q", "-m", "feat: model", cwd=tree)

    sha = trees.merge_card(root, "ms/mvp", "tk-a11111", "tk-a11111")
    assert run.must("rev-parse", "ms/mvp", cwd=root) == sha


def test_the_milestone_branch_and_the_card_both_reach_origin_on_a_merge(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    bare = origin_for(root, tmp_path / "origin.git")
    tree = trees.ensure_card(root, "tk-a11111", "tk-a11111", "ms/mvp")
    (tree / "models.py").write_text("class Invoice: ...\n", encoding="utf-8")
    run.must("add", "-A", cwd=tree)
    run.must("commit", "-q", "-m", "feat: model", cwd=tree)

    sha = trees.merge_card(root, "ms/mvp", "tk-a11111", "tk-a11111")
    assert run.must("rev-parse", "ms/mvp", cwd=bare) == sha
    assert run.git("rev-parse", "--verify", "tk-a11111", cwd=bare).ok


# ── binding ─────────────────────────────────────────────────────────────────


class FakeBoard:
    def __init__(self, working: bool = True) -> None:
        self.working = working
        self.calls: list[dict[str, Any]] = []

    def call(self, verb: str, args: dict[str, Any]) -> dict[str, Any]:
        if not self.working:
            raise TaskopsError("the board did not answer")
        self.calls.append({"verb": verb, **args})
        return {"ok": True}


def committed(root: Path, card: str) -> None:
    run.must("checkout", "-q", "-b", card, cwd=root)
    (root / f"{card}.py").write_text("x = 1\n", encoding="utf-8")
    run.must("add", "-A", cwd=root)
    run.must("commit", "-q", "-m", f"feat: {card}\n\nTask: {card}", cwd=root)


def test_a_commit_carries_its_card_its_sha_and_its_files(tmp_path: Path) -> None:
    root = repo(tmp_path)
    committed(root, "tk-a11111")
    facts = bind.commit_facts(root)
    assert facts is not None
    assert facts["task"] == "tk-a11111" and facts["files"] == ["tk-a11111.py"]
    assert facts["subject"] == "feat: tk-a11111" and len(facts["sha"]) == 40


def test_a_commit_carries_plus_minus_per_file_beside_its_files(tmp_path: Path) -> None:
    """Additive: `files` is byte-identical to what it always was — the edit
    surface and collisions() read it — and `numstat` rides beside it."""
    root = repo(tmp_path)
    (root / "grew.py").write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")
    (root / "README.md").write_text("bye\n", encoding="utf-8")
    run.must("add", "-A", cwd=root)
    run.must("commit", "-q", "-m", "feat: two\n\nTask: tk-a11111", cwd=root)

    facts = bind.commit_facts(root)
    assert facts is not None
    assert facts["files"] == ["README.md", "grew.py"]
    assert facts["numstat"] == {"README.md": [1, 1], "grew.py": [3, 0]}


def test_a_binary_file_counts_as_null_not_zero(tmp_path: Path) -> None:
    """git prints `-` for a binary. "cannot be counted" is not "nothing
    changed", and 0 would say the second."""
    root = repo(tmp_path)
    (root / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x01\x02\x03")
    run.must("add", "-A", cwd=root)
    run.must("commit", "-q", "-m", "feat: logo\n\nTask: tk-a11111", cwd=root)

    facts = bind.commit_facts(root)
    assert facts is not None
    assert facts["numstat"] == {"logo.png": None}


def test_a_rename_is_keyed_by_the_path_files_reports(tmp_path: Path) -> None:
    """The human --numstat writes `{old => new}` on a rename; -z gives the real
    new path, so the key matches the name in `files`."""
    root = repo(tmp_path)
    run.must("mv", "README.md", "READ.md", cwd=root)
    run.must("commit", "-q", "-m", "chore: rename\n\nTask: tk-a11111", cwd=root)

    facts = bind.commit_facts(root)
    assert facts is not None
    assert facts["files"] == ["READ.md"]
    assert set(facts["numstat"]) == {"READ.md"}


def test_a_commit_with_no_card_is_still_facts_with_no_task(tmp_path: Path) -> None:
    """Nobody is forced to take a card to commit. The board just learns that
    this sha happened outside any card — task is empty, and the bind verb files
    it at project level. (This replaced a pin of the old drop-it-silently
    behaviour, changed on the owner's request, 2026-08-07.)"""
    root = repo(tmp_path)
    facts = bind.commit_facts(root)  # the first commit, on main
    assert facts is not None and facts["task"] == "" and facts["subject"] == "first"


def test_a_bind_the_server_refused_is_queued_and_drained_later(tmp_path: Path) -> None:
    """v1 lost it forever and the card could never close."""
    root = repo(tmp_path)
    committed(root, "tk-a11111")
    facts = bind.commit_facts(root)
    assert facts is not None

    down = FakeBoard(working=False)
    with pytest.raises(TaskopsError, match="queued"):
        bind.record(down, root, facts)
    assert (root / bind.PENDING).exists()

    back = FakeBoard()
    assert bind.drain(back, root) == 1
    assert back.calls[0]["verb"] == "bind" and back.calls[0]["task"] == "tk-a11111"
    assert not (root / bind.PENDING).exists()
    assert bind.drain(back, root) == 0  # nothing left, and no error


# ── installing ──────────────────────────────────────────────────────────────


def test_install_writes_two_hooks_and_ignores_the_secret(tmp_path: Path) -> None:
    root = repo(tmp_path)
    assert sorted(install.install_hooks(root, "/usr/bin/python3")) == [
        "post-commit",
        "prepare-commit-msg",
    ]
    install.write_config(root, "https://example.test/facturador", "s3cret")
    install.write_gitignore(root)
    install.write_mcp(root, "/usr/bin/python3", "dev:berna")

    assert (root / ".taskops" / "remote.json").stat().st_mode & 0o777 == 0o600
    assert ".taskops/remote.json" in (root / ".gitignore").read_text(encoding="utf-8")
    assert "taskops" in (root / ".mcp.json").read_text(encoding="utf-8")
    for name in install.HOOKS:
        hook = root / ".git" / "hooks" / name
        assert hook.stat().st_mode & 0o100  # executable


def test_a_foreign_hook_is_never_overwritten(tmp_path: Path) -> None:
    root = repo(tmp_path)
    mine = root / ".git" / "hooks" / "post-commit"
    mine.write_text("#!/bin/sh\necho theirs\n", encoding="utf-8")
    written = install.install_hooks(root, "/usr/bin/python3")
    assert "post-commit (kept: not ours)" in written
    assert "theirs" in mine.read_text(encoding="utf-8")


def test_mcp_config_keeps_the_other_servers(tmp_path: Path) -> None:
    root = repo(tmp_path)
    (root / ".mcp.json").write_text('{"mcpServers": {"axion": {"command": "x"}}}', encoding="utf-8")
    install.write_mcp(root, "/usr/bin/python3", "dev:berna")
    import json

    config: Any = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
    assert set(config["mcpServers"]) == {"axion", "taskops"}


# ── finding the project ─────────────────────────────────────────────────────


def test_a_bare_taskops_directory_above_is_not_a_project(tmp_path: Path) -> None:
    """The bug this exists to prevent, found on the first real `init`.

    v1 kept its sessions in `~/.taskops/`, so that directory exists on every
    machine that ever ran it. Matching the DIRECTORY made HOME a project: a
    fresh repo under it walked up, adopted HOME, and wrote the board, two git
    hooks, `.mcp.json` and a Claude settings entry there instead of in the
    repo. The address FILE is what makes a project, and only `init`/`join`
    write it.
    """
    home = tmp_path / "home"
    (home / ".taskops").mkdir(parents=True)
    (home / ".taskops" / "sessions.json").write_text("{}", encoding="utf-8")  # v1's leftover
    project = repo(home, "work")  # a git repo underneath it

    assert board.find_root(project) == project  # NOT home
    assert not board.is_project(home)

    # ...and a directory that is not a project gets NO board, not an empty one:
    # the MCP server is registered globally, so `open_board` runs in every repo
    # there is, and `LocalBoard` makes its directories on construction.
    absent = board.open_board(project, "dev:berna")
    with pytest.raises(NotFound, match="taskops init"):
        absent.call("board", {})
    assert not (project / ".taskops").exists()  # a read created nothing

    # ...and once a board really is there, the walk finds it from anywhere in it
    (project / ".taskops").mkdir()
    (project / ".taskops" / "board.json").write_text("{}", encoding="utf-8")
    deep = project / "src" / "deep"
    deep.mkdir(parents=True)
    assert board.find_root(deep) == project
