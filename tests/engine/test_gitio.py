"""The git conventions — the branch shape and the trailer.

The parsing tests run on strings; the repository tests shell out to git, because everything
in `gitio` is a CLAIM ABOUT GIT'S BEHAVIOUR and only git can confirm one.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from taskops.engine import gitio


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)


def test_a_branch_names_its_task() -> None:
    assert gitio.task_of_branch("tk/tk-4f2a9c/fix-the-thing") == "tk-4f2a9c"


def test_a_near_miss_is_not_a_match() -> None:
    """Anchored on purpose: a near-miss must read as UNBOUND rather than bind to the wrong
    task, because a wrong association is worse than a missing one — the board would show
    evidence for a task that has none, and the `done` guard would let it close."""
    for branch in ("feat/tk-4f2a9c/x", "tk-4f2a9c", "tk/tk-4f2a9c",
                   "tk/nope/x", "tk/tk-ZZZZ/x"):
        assert gitio.task_of_branch(branch) == "", branch


def test_a_trailer_is_found_and_is_case_insensitive() -> None:
    """Case-insensitive because a human types `task:` as readily as `Task:`, and the trailer
    is the binding that survives a squash — losing one to capitalisation would be silent."""
    assert gitio.task_of_message("Fix it\n\nTask: tk-4f2a9c\n") == "tk-4f2a9c"
    assert gitio.task_of_message("Fix it\n\ntask: tk-4f2a9c") == "tk-4f2a9c"


def test_a_trailer_must_be_its_own_line() -> None:
    """Prose that mentions a task is not a binding.

    "This relates to Task: tk-1 in passing" would otherwise bind the commit, and a commit
    bound by a sentence somebody wrote is a commit nobody can trust the attribution of.
    """
    assert gitio.task_of_message("see Task: tk-4f2a9c for context") == ""


def test_adding_a_trailer_is_idempotent() -> None:
    """The guard runs on every commit, so an agent that wrote the trailer by hand must not
    get two."""
    once = gitio.add_trailer("Fix the parser", "tk-4f2a9c")
    assert once.count("Task:") == 1
    assert gitio.add_trailer(once, "tk-4f2a9c") == once


def test_a_trailer_for_another_task_is_left_alone() -> None:
    """Rewriting what the author said would be worse than refusing: the guard rejects the
    mismatch instead, so a human decides which of the two is wrong."""
    message = "Fix it\n\nTask: tk-aaaaaa\n"
    assert gitio.add_trailer(message, "tk-bbbbbb") == message


def test_the_branch_is_read_in_a_repository_with_no_commits(tmp_path: Path) -> None:
    """THE bug this function was rewritten for.

    On an unborn HEAD `rev-parse --abbrev-ref HEAD` fails, so the branch read as "" and the
    guard told an agent that the task branch it was standing on was not a task branch. Every
    test had made an initial commit first, so only hand-driving the CLI found it.
    """
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "checkout", "-q", "-b", "tk/tk-4f2a9c/fresh")
    assert gitio.current_branch(tmp_path) == "tk/tk-4f2a9c/fresh"


def test_a_detached_head_has_no_branch(tmp_path: Path) -> None:
    """`rev-parse --abbrev-ref` answers the literal "HEAD" here, which is indistinguishable
    from a branch of that name. Failing is the honest answer: there is no branch."""
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "a@b.c")
    git(tmp_path, "config", "user.name", "A")
    (tmp_path / "f").write_text("x", encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "one")
    git(tmp_path, "checkout", "-q", "--detach")
    assert gitio.current_branch(tmp_path) == ""


def test_git_absent_degrades_to_empty(tmp_path: Path) -> None:
    """Not a repository at all. Every reader here must degrade, because this code runs inside
    git hooks and in directories that are sometimes not repositories."""
    assert gitio.current_branch(tmp_path) == ""
    assert gitio.head_sha(tmp_path) == ""
    assert gitio.changed_files(tmp_path) == []


@pytest.mark.parametrize("title,expected", [
    ("Fix the WAL pragma!! (urgent)", "fix-the-wal-pragma-urgent"),
    ("  spaces   everywhere  ", "spaces-everywhere"),
    ("///", "task"),
    ("", "task"),
])
def test_a_title_becomes_a_branch_safe_slug(title: str, expected: str) -> None:
    """Lossy and never parsed back — the id identifies the task, so this only has to be
    readable in a `git branch` listing. "task" is the floor: a branch cannot end up as
    `tk/tk-1/` with nothing after the slash."""
    from taskops._ids import slugify

    assert slugify(title) == expected
