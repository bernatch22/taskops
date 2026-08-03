"""The wiring, proven by git rather than by argparse.

This is the test the rename needed. Every line `taskops init` writes into `.git/hooks` ends in
`|| true`, so a command that no longer exists does not fail — it does NOTHING, and commits
quietly stop being bound to cards. Nobody finds out until somebody reads a board and wonders
where the commits went.

So nothing here is mocked and nothing here reaches into Python. A real repository, a real
`git commit`, and then the question that matters: is the commit on the card? Only the real
hook, running the real module from git's own environment, can answer it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from taskops.usecases import ask, init, next_task, plan
from taskops.usecases.hooks import MARKER
from taskops.usecases.milestone import open_chapter

MODULE = "taskops.transports.hooks"
"""The one string this whole file exists to protect. It appears in `usecases.hooks.runner`,
in `plugin/hooks/hooks.json`, and nowhere a type checker can see."""


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "berna@example.com")
    git(tmp_path, "config", "user.name", "Berna")
    (tmp_path / "README.md").write_text("start\n", encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "initial")
    # Every card belongs to a chapter: the fixture opens one so the test can be about its own
    # subject rather than about that.
    init(tmp_path)
    open_chapter(tmp_path, "the chapter these tests plan into",
                 actor="dev:berna")
    return tmp_path


def test_the_module_git_is_told_to_run_actually_runs() -> None:
    """The cheapest half: the entry point exists as an executable module.

    Run as a SUBPROCESS, not imported, because `python -m` is what a hook line says and an
    importable package with no `__main__` fails only that way.
    """
    done = subprocess.run([sys.executable, "-m", MODULE, "--help"],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    for event in ("pre-tool-use", "session-start", "commit", "ingest", "sync"):
        assert event in done.stdout


def test_the_installed_hooks_name_the_wiring_transport_not_the_cli(repo: Path) -> None:
    """The CLI is the developer's door. A hook line pointing at it is the separation being
    cosmetic, which is the whole reason this module exists."""
    for name in ("post-commit", "post-checkout", "post-merge"):
        line = (repo / ".git" / "hooks" / name).read_text(encoding="utf-8")
        assert f"-m {MODULE}" in line, f"{name} does not run the wiring transport"
        assert "cli.main" not in line, f"{name} still enters through the developer's CLI"


def test_a_real_commit_on_a_card_branch_is_bound_by_the_installed_hook(repo: Path) -> None:
    """THE test. plan → claim → branch → `git commit` → is it on the card?

    Nothing calls `ingest` here. The only thing that could have recorded this commit is
    `.git/hooks/post-commit`, running the module named in it, found by the interpreter
    embedded in it. If the name is wrong the assertion reads `0 == 1` and says so — which is
    the failure mode `|| true` otherwise hides completely.
    """
    planned = plan(repo, [{"title": "Bind me", "spec": "x"}], actor="agent:berna/one")
    task_id = planned["created"][0]["id"]
    claimed = next_task(repo, actor="agent:berna/one", task=task_id)
    assert claimed["claim"] is not None
    git(repo, "switch", "-q", "-c", claimed["claim"]["branch"])

    (repo / "bound.py").write_text("x = 1\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", f"Bind me\n\nTask: {task_id}")

    view = ask(repo, task_id, actor="agent:berna/one")
    assert len(view["commits"]) == 1, "post-commit did not bind the commit to the card"


def test_init_repairs_a_hook_left_pointing_at_the_old_command(repo: Path) -> None:
    """A repository initialised before the wiring moved has a hook naming a module that is
    gone, and `|| true` means it never says so. `taskops init` again is the documented repair,
    so it has to actually rewrite the line — reporting "already installed" over a dead command
    would make the repair the thing that hides the damage."""
    hook = repo / ".git" / "hooks" / "post-commit"
    stale = f"#!/bin/sh\n{MARKER}\n{sys.executable} -m taskops.transports.cli.main " \
            "ingest commit HEAD >/dev/null 2>&1 || true\n"
    hook.write_text(stale, encoding="utf-8")

    init(repo)
    open_chapter(repo, "the chapter these tests plan into",
                 actor="dev:berna")

    after = hook.read_text(encoding="utf-8")
    assert f"-m {MODULE} ingest commit HEAD" in after
    assert "cli.main" not in after


def test_repairing_keeps_the_repositorys_own_hook(repo: Path) -> None:
    """Only OUR line below the marker moves. Deleting somebody's linter to fix our own
    rename would deserve everything that followed."""
    hook = repo / ".git" / "hooks" / "post-commit"
    hook.write_text(f"#!/bin/sh\necho mine\n\n{MARKER}\nold-command || true\n",
                    encoding="utf-8")
    init(repo)
    open_chapter(repo, "the chapter these tests plan into",
                 actor="dev:berna")
    after = hook.read_text(encoding="utf-8")
    assert "echo mine" in after
    assert "old-command" not in after
    assert f"-m {MODULE}" in after
