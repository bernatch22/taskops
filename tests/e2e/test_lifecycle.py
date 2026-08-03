"""The whole loop, against a REAL git repository with the REAL hooks installed.

This is the test that would have caught every integration bug the unit tests cannot see: a
hook line that does not run, a branch name the guard's pattern rejects, a trailer written in
a form `ingest` cannot read back. It shells out to git on purpose — the conventions in
`gitio` are claims about git's behaviour, and only git can confirm them.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from taskops.transports.hooks.__main__ import main
from taskops.usecases import ask, check_commit, init, next_task, plan, update
from taskops.usecases.milestone import open_chapter


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          check=True)
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repository with an identity and one commit, then `taskops init`."""
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


def test_init_installs_the_hooks_and_ignores_the_cache(repo: Path) -> None:
    for hook in ("post-commit", "post-checkout", "post-merge"):
        installed = repo / ".git" / "hooks" / hook
        assert installed.is_file(), f"{hook} was not installed"
        assert "taskops" in installed.read_text(encoding="utf-8")
    assert "db.sqlite" in (repo / ".gitignore").read_text(encoding="utf-8")


def test_init_chains_onto_an_existing_hook(tmp_path: Path) -> None:
    """A repository's own post-commit must survive. Deleting somebody's linter to install a
    task tracker would deserve everything that followed."""
    git(tmp_path, "init", "-q")
    hook = tmp_path / ".git" / "hooks" / "post-commit"
    hook.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
    init(tmp_path)
    open_chapter(tmp_path, "the chapter these tests plan into",
                 actor="dev:berna")
    after = hook.read_text(encoding="utf-8")
    assert "echo mine" in after
    assert "-m taskops.transports.hooks ingest commit HEAD" in after
    # The absolute interpreter, not a bare `taskops`: git hooks run with git's environment,
    # which routinely cannot see the virtualenv taskops is installed in.
    assert sys.executable in after


def test_the_full_loop_from_plan_to_done(repo: Path) -> None:
    """plan → next → branch → commit (guarded) → ingest → done.

    The one test that proves the parts fit. Every step here is the step an agent takes, in
    the order it takes them.
    """
    planned = plan(repo, [{"title": "Add the health endpoint",
                           "spec": "Return 200 with a version string.",
                           "files": ["server.py"]}], actor="agent:berna/one")
    task_id = planned["created"][0]["id"]
    assert planned["unblocked"] == [task_id], "a task with no deps must be ready at once"

    claimed = next_task(repo, actor="agent:berna/one", session="sess-1")
    assert claimed["claim"] is not None
    branch = claimed["claim"]["branch"]
    assert branch.startswith(f"tk/{task_id}/")

    git(repo, "switch", "-q", "-c", branch)
    verdict = check_commit(repo, "Add the health endpoint", actor="agent:berna/one")
    assert verdict.allowed, verdict.reason
    assert f"Task: {task_id}" in verdict.message, "the guard must add the trailer"

    (repo / "server.py").write_text("def health():\n    return 200\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", verdict.message)

    # The post-commit hook ran as part of `git commit`, so the association already exists.
    view = ask(repo, task_id, actor="agent:berna/one")
    assert len(view["commits"]) == 1, "post-commit did not record the commit"

    closed = update(repo, task_id, actor="agent:berna/one", status="done",
                    comment="Endpoint added and committed.")
    assert closed["task"]["status"] == "done"


def test_a_commit_without_a_claim_is_denied(repo: Path) -> None:
    """The enforcement, end to end. An unclaimed commit must never exist."""
    planned = plan(repo, [{"title": "Unclaimed work", "spec": "x"}])
    task_id = planned["created"][0]["id"]
    git(repo, "switch", "-q", "-c", f"tk/{task_id}/unclaimed-work")

    verdict = check_commit(repo, "sneak this in", actor="agent:berna/nobody")
    assert not verdict.allowed
    assert "no live lease" in verdict.reason


def test_closing_without_a_commit_is_refused(repo: Path) -> None:
    """THE guard that makes the board trustworthy, proven against a real repository."""
    planned = plan(repo, [{"title": "Claims to be done", "spec": "x"}])
    task_id = planned["created"][0]["id"]
    next_task(repo, actor="agent:berna/one", task=task_id)
    update(repo, task_id, actor="agent:berna/one", comment="on it")

    from taskops import GuardFailed

    with pytest.raises(GuardFailed) as caught:
        update(repo, task_id, actor="agent:berna/one", status="done", comment="trust me")
    assert "no commit bound" in str(caught.value)

    # …and the documented escape hatch works, with its justification.
    closed = update(repo, task_id, actor="agent:berna/one", status="done", no_code=True,
                    comment="Decided against the change; reasoning in the thread.")
    assert closed["task"]["status"] == "done"


def test_the_commit_hook_denies_with_exit_code_two(repo: Path) -> None:
    """Claude Code reads code 2 as DENY and shows stderr to the MODEL. Any other code lets
    the commit through, so the exact number is load-bearing."""
    planned = plan(repo, [{"title": "Guarded", "spec": "x"}])
    task_id = planned["created"][0]["id"]
    git(repo, "switch", "-q", "-c", f"tk/{task_id}/guarded")
    code = main(["commit", "--repo", str(repo), "--message", "nope",
                 "--actor", "agent:berna/nobody"])
    assert code == 2


def test_the_guard_fails_open_when_taskops_cannot_run(tmp_path: Path) -> None:
    """A directory with no project at all. The guard must ALLOW.

    Fail-open is the deliberate choice: blocking a developer's commit because taskops is
    missing or broken would make the tool something people uninstall.
    """
    assert main(["commit", "--repo", str(tmp_path), "--message", "x"]) == 0
