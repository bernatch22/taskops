"""gitwork/ — against real repositories in tmp_path. No mocks: git is the point."""

from __future__ import annotations

from typing import Any
from pathlib import Path

import pytest

from taskops import board
from taskops._errors import Refused, NotFound, TaskopsError
from taskops.gitwork import (
    run,
    bind,
    diff,
    patch,
    trees,
    remote,
    install,
    landing,
    trailer,
    claudefiles,
)


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

    sha = landing.merge_card(root, "ms/mvp", "tk-a11111", "tk-a11111")
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
        landing.merge_card(root, "ms/mvp", "tk-d44444", "tk-d44444")
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
    assert landing.merge_card(root, "ms/mvp", "tk-d44444", "tk-d44444")  # now it lands


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

    sha = landing.merge_card(root, "ms/mvp", "tk-a11111", "tk-a11111")
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

    sha = landing.merge_card(root, "ms/mvp", "tk-a11111", "tk-a11111")
    assert run.must("rev-parse", "ms/mvp", cwd=bare) == sha
    assert run.git("rev-parse", "--verify", "tk-a11111", cwd=bare).ok


def test_a_push_lands_on_the_branch_it_names_and_never_on_its_upstream(
    tmp_path: Path,
) -> None:
    """The one-sided refspec bug, pinned by the config that exposed it.

    `git push origin <name>` reads as "push that branch there" and does not mean
    it: with no colon, git resolves the destination through `push.default`, and
    under `upstream` the destination is whatever the branch TRACKS. On
    2026-08-10 this repo's own milestone branches still tracked `origin/main`
    from v1, so the best-effort visibility push was quietly landing integration
    branches on the trunk — inside a function that swallows every error, in a
    tool whose central rule is that only the human lands anything there.
    """
    root = repo(tmp_path)
    bare = origin_for(root, tmp_path / "origin.git")
    remote.push(root, "main")
    trunk = run.must("rev-parse", "main", cwd=bare)
    run.must("config", "push.default", "upstream", cwd=root)
    run.must("branch", "ms/mvp", cwd=root)
    run.must("branch", "--set-upstream-to", "origin/main", "ms/mvp", cwd=root)
    (root / "models.py").write_text("class Invoice: ...\n", encoding="utf-8")
    run.must("add", "-A", cwd=root)
    run.must("commit", "-q", "-m", "feat: model", cwd=root)
    run.must("branch", "-f", "ms/mvp", "HEAD", cwd=root)

    remote.push(root, "ms/mvp")
    assert run.must("rev-parse", "ms/mvp", cwd=bare) == run.must(
        "rev-parse", "ms/mvp", cwd=root
    )
    assert run.must("rev-parse", "main", cwd=bare) == trunk  # the trunk never moved


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
    claudefiles.write_mcp(root, "/usr/bin/python3", "dev:berna")

    assert (root / ".taskops" / "remote.json").stat().st_mode & 0o777 == 0o600
    assert ".taskops/remote.json" in (root / ".gitignore").read_text(encoding="utf-8")
    assert "taskops" in (root / ".mcp.json").read_text(encoding="utf-8")
    for name in install.HOOKS:
        hook = root / ".git" / "hooks" / name
        assert hook.stat().st_mode & 0o100  # executable


def test_everything_a_checkout_makes_for_itself_is_ignored(tmp_path: Path) -> None:
    """The two that were missing cost nothing until they were noticed as untracked
    forever: `taskops ui` mints a credential into `.taskops/live.sqlite`, and
    `board push` archives the local history as `.taskops/board.local-<date>/`.
    Committing that archive would put a SECOND history of the same board in the
    repo, which is exactly what `board.ingest` refuses on the wire."""
    root = repo(tmp_path)
    install.write_gitignore(root)
    ignored = (root / ".gitignore").read_text(encoding="utf-8")
    assert ".taskops/live.sqlite*" in ignored
    assert ".taskops/board.local-*/" in ignored

    (root / ".taskops").mkdir(exist_ok=True)
    (root / ".taskops" / "live.sqlite").write_text("x", encoding="utf-8")
    (root / ".taskops" / "board.local-2026-08-09").mkdir()
    (root / ".taskops" / "board.local-2026-08-09" / "events.jsonl").write_text("{}", encoding="utf-8")
    untracked = run.git("status", "--porcelain", "--untracked-files=all", cwd=root).out
    assert "live.sqlite" not in untracked, untracked
    assert "board.local" not in untracked, untracked


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
    claudefiles.write_mcp(root, "/usr/bin/python3", "dev:berna")
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


# ── the repo's web home (gitwork/remote.py) ─────────────────────────────────


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("git@github.com:owner/repo.git", ("github.com", "owner/repo")),
        ("ssh://git@github.com/owner/repo.git", ("github.com", "owner/repo")),
        ("https://github.com/owner/repo", ("github.com", "owner/repo")),
        ("https://user:token@gitlab.com/group/sub/repo.git", ("gitlab.com", "group/sub/repo")),
        ("ssh://git@ssh.gitlab.com:2222/group/repo.git", ("ssh.gitlab.com", "group/repo")),
        ("git://github.com/owner/repo.git", ("github.com", "owner/repo")),
    ],
)
def test_every_origin_form_parses_to_the_same_shape(
    url: str, expected: tuple[str, str]
) -> None:
    found = remote.parse(url)
    assert found is not None
    assert (found["host"], found["slug"]) == expected
    assert found["url"] == f"https://{expected[0]}/{expected[1]}"


@pytest.mark.parametrize("url", ["", "   ", "/srv/mirrors/repo.git", "../sibling", "github.com"])
def test_an_origin_that_is_not_a_web_home_parses_to_nothing(url: str) -> None:
    """A local path or a bare host is not a page anybody can link to."""
    assert remote.parse(url) is None


def test_init_records_the_origin_and_join_updates_it(tmp_path: Path) -> None:
    """The write comes from the side that HAS the repo, at the two commands that
    already touch the board — and a re-run with a changed origin wins."""
    root = repo(tmp_path)
    run.must("remote", "add", "origin", "git@github.com:owner/repo.git", cwd=root)
    from taskops.cli import commands

    commands.init(root)
    opened = board.open_board(root, "dev:berna")
    assert opened.call("board", {})["repo"] == {
        "host": "github.com",
        "slug": "owner/repo",
        "url": "https://github.com/owner/repo",
    }
    opened.close()

    run.must("remote", "set-url", "origin", "https://gitlab.com/team/repo.git", cwd=root)
    commands.init(root)
    opened = board.open_board(root, "dev:berna")
    assert opened.call("board", {})["repo"]["slug"] == "team/repo"
    opened.close()


def test_no_origin_records_nothing_and_nothing_appears(tmp_path: Path) -> None:
    """The chapter's third rule: a board without a remote behaves like today."""
    root = repo(tmp_path)
    from taskops.cli import commands

    commands.init(root)
    opened = board.open_board(root, "dev:berna")
    assert opened.call("board", {})["repo"] is None
    assert opened.call("board", {})["seq"] == 0  # not one event was written
    opened.close()


# ── diff: the read-only door's engine ───────────────────────────────────────


def merged(root: Path) -> str:
    """A repo with a REAL merge commit: main gains a file, a side branch gains
    two, and main merges it --no-ff. That is the shape a landed card has."""
    (root / "on-main.txt").write_text("main\n", encoding="utf-8")
    run.must("add", "-A", cwd=root)
    run.must("commit", "-q", "-m", "on main", cwd=root)
    run.must("checkout", "-q", "-b", "side", cwd=root)
    for name in ("a.txt", "b.txt"):
        (root / name).write_text(f"{name}\n", encoding="utf-8")
        run.must("add", "-A", cwd=root)
        run.must("commit", "-q", "-m", f"add {name}", cwd=root)
    run.must("checkout", "-q", "main", cwd=root)
    (root / "later.txt").write_text("later\n", encoding="utf-8")
    run.must("add", "-A", cwd=root)
    run.must("commit", "-q", "-m", "later on main", cwd=root)
    run.must("merge", "-q", "--no-ff", "-m", "merge side", "side", cwd=root)
    return run.must("rev-parse", "HEAD", cwd=root)


def test_a_ref_the_repo_lacks_resolves_to_none_and_runs_no_diff(tmp_path: Path) -> None:
    """The refusal is BEFORE any diff — an unknown ref never becomes a range."""
    root = repo(tmp_path)
    assert diff.resolve(root, "nope") is None
    assert diff.commit_range(root, "nope") is None
    assert diff.compare_range(root, "main", "nope") is None


@pytest.mark.parametrize(
    "hostile",
    [
        "--upload-pack=touch /tmp/pwned",
        "-o",
        "main; touch /tmp/pwned",
        "main && rm -rf /",
        "$(whoami)",
        "`id`",
        "main\nHEAD",
        "main | cat",
        "'main'",
        "main\x00",
    ],
)
def test_an_injection_shaped_ref_never_reaches_git(tmp_path: Path, hostile: str) -> None:
    """THE security test. A ref arrives from a browser: it is refused by shape
    (an option, or a byte a ref may not carry) and, past that, only the resolved
    40-hex sha is ever used. Nothing is ever interpolated into a command."""
    root = repo(tmp_path)
    assert not diff.usable(hostile), f"{hostile!r} passed the shape guard"
    assert diff.resolve(root, hostile) is None
    assert diff.commit_range(root, hostile) is None
    assert diff.compare_range(root, "main", hostile) is None


def test_a_legitimate_branch_name_with_slashes_still_resolves(tmp_path: Path) -> None:
    """The guard must not be so tight it refuses `ms/<slug>` — taskops' own
    branch shape — or the door would be useless on every real board."""
    root = repo(tmp_path)
    run.must("branch", "ms/the-chapter", cwd=root)
    got = diff.resolve(root, "ms/the-chapter")
    assert got is not None and len(got) == 40


def test_a_merge_commit_diffs_against_its_first_parent_only(tmp_path: Path) -> None:
    """The whole point of the chosen spelling: `git diff <sha>^1 <sha>`. A merge
    that exploded into its branch's whole diff would make every landed card's
    patch useless — here the merge shows the side branch's two files, and NOT
    `later.txt`, which main gained on the first-parent side."""
    root = repo(tmp_path)
    sha = merged(root)
    found = diff.commit_range(root, sha)
    assert found is not None
    counted = patch.stat(root, *found)
    assert sorted(counted) == ["a.txt", "b.txt"]
    assert "later.txt" not in counted


def test_a_root_commit_diffs_against_the_empty_tree(tmp_path: Path) -> None:
    """No parent is not "no diff": the first commit of a repo is everything it
    added, and git's own empty tree is what says so."""
    root = repo(tmp_path)
    first = run.must("rev-list", "--max-parents=0", "HEAD", cwd=root)
    found = diff.commit_range(root, first)
    assert found == (diff.EMPTY_TREE, first)
    assert "README.md" in patch.stat(root, *found)


def test_a_compare_is_what_the_head_adds_over_the_merge_base(tmp_path: Path) -> None:
    """The card-as-PR read, taken as of the moment the card was still open —
    the milestone tip is the merge's first parent. `later.txt` landed on that
    side AFTER the branch point, so it is not part of what the branch adds."""
    root = repo(tmp_path)
    sha = merged(root)
    found = diff.compare_range(root, f"{sha}^1", "side")
    assert found is not None
    counted = patch.stat(root, *found)
    assert sorted(counted) == ["a.txt", "b.txt"]


def test_an_integrated_card_compares_against_the_merge_s_first_parent(
    tmp_path: Path,
) -> None:
    """THE bug the Worktrees screen showed: every row said "no files differ".
    Once `side` is merged, merge-base(main, side) IS side's head and the range
    is empty — correct and useless. The base comes off the merge that landed
    it, so the card still reads as the pull request it was: a.txt and b.txt,
    and NOT `later.txt`, which the CHAPTER gained while the card was open and
    which a bare first parent would render as this card deleting it."""
    root = repo(tmp_path)
    sha = merged(root)
    found = diff.compare_range(root, "main", "side")
    assert found is not None
    assert found[0] == run.must("rev-parse", f"{sha}^1~1", cwd=root)
    assert found[1] == run.must("rev-parse", "side", cwd=root)
    counted = patch.stat(root, *found)
    assert sorted(counted) == ["a.txt", "b.txt"]


def test_the_merge_that_counts_is_the_one_that_brought_the_card_in(
    tmp_path: Path,
) -> None:
    """A card is merged into its chapter and the chapter is later merged into
    main, so the ancestry path from the card carries TWO merges. Only the
    OLDEST one landed this card; the newest landed the whole chapter, and
    reading its first parent would put the base out on main and drag the
    chapter's other work into the card's diff."""
    root = repo(tmp_path)
    run.must("checkout", "-q", "-b", "chapter", cwd=root)
    (root / "sibling.txt").write_text("sibling\n", encoding="utf-8")
    run.must("add", "-A", cwd=root)
    run.must("commit", "-q", "-m", "a sibling card", cwd=root)
    branch_point = run.must("rev-parse", "HEAD", cwd=root)
    run.must("checkout", "-q", "-b", "side", cwd=root)
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    run.must("add", "-A", cwd=root)
    run.must("commit", "-q", "-m", "add a", cwd=root)
    run.must("checkout", "-q", "chapter", cwd=root)
    run.must("merge", "-q", "--no-ff", "-m", "merge side", "side", cwd=root)
    run.must("checkout", "-q", "main", cwd=root)
    run.must("merge", "-q", "--no-ff", "-m", "merge chapter", "chapter", cwd=root)

    found = diff.compare_range(root, "main", "side")
    assert found is not None and found[0] == branch_point
    assert sorted(patch.stat(root, *found)) == ["a.txt"]


def test_a_fast_forwarded_branch_keeps_the_empty_range_rather_than_guess(
    tmp_path: Path,
) -> None:
    """No merge commit on the ancestry path — this board never fast-forwards,
    another clone might. There is no "as it stood before" to point at, so the
    honest answer is the empty range, not an invented base."""
    root = repo(tmp_path)
    run.must("checkout", "-q", "-b", "side", cwd=root)
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    run.must("add", "-A", cwd=root)
    run.must("commit", "-q", "-m", "add a", cwd=root)
    run.must("checkout", "-q", "main", cwd=root)
    run.must("merge", "-q", "--ff-only", "side", cwd=root)
    head = run.must("rev-parse", "side", cwd=root)
    assert diff.compare_range(root, "main", "side") == (head, head)
    assert patch.stat(root, head, head) == {}


def test_the_numstat_vocabulary_is_the_one_bind_already_writes(tmp_path: Path) -> None:
    """[added, deleted] per file, None for a binary — one vocabulary for +/-
    everywhere in the UI, whether it came from an event or from this door."""
    root = repo(tmp_path)
    (root / "text.txt").write_text("one\ntwo\n", encoding="utf-8")
    (root / "blob.bin").write_bytes(b"\x00\x01\x02\xff")
    run.must("add", "-A", cwd=root)
    run.must("commit", "-q", "-m", "mixed", cwd=root)
    found = diff.commit_range(root, "HEAD")
    assert found is not None
    assert patch.stat(root, *found) == {"text.txt": [2, 0], "blob.bin": None}


def test_a_patch_over_the_cap_is_truncated_AND_flagged(tmp_path: Path) -> None:
    """Never silently cut: a cut patch that does not say so is a lie."""
    root = repo(tmp_path)
    (root / "big.txt").write_text("a line that is quite long\n" * 400, encoding="utf-8")
    run.must("add", "-A", cwd=root)
    run.must("commit", "-q", "-m", "big", cwd=root)
    found = diff.commit_range(root, "HEAD")
    assert found is not None
    text, cut = patch.patch(root, *found, cap=500)
    assert cut and len(text.encode()) <= 500
    whole, uncut = patch.patch(root, *found)
    assert not uncut and len(whole) > 500
    payload = patch.between(root, *found, cap=500)
    assert payload["truncated"] is True and payload["cap"] == 500


def test_a_path_filter_narrows_the_patch_and_is_never_an_option(tmp_path: Path) -> None:
    root = repo(tmp_path)
    for name in ("one.txt", "two.txt"):
        (root / name).write_text(f"{name}\n", encoding="utf-8")
    run.must("add", "-A", cwd=root)
    run.must("commit", "-q", "-m", "two files", cwd=root)
    found = diff.commit_range(root, "HEAD")
    assert found is not None
    text, _ = patch.patch(root, *found, path="one.txt")
    assert "one.txt" in text and "two.txt" not in text
    # A path is user input too. After `--` git cannot read it as an option —
    # and the proof is a file that is NOT written. It lives under tmp_path, so
    # a mutant that DOES write it cannot poison the next run.
    written = tmp_path / "tk-d50e0a-pwned"
    hostile, _ = patch.patch(root, *found, path=f"--output={written}")
    assert hostile == "" and not written.exists()
