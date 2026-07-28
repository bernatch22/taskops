"""Rewriting a card, and that rewrite surviving the trip through git to another clone.

A spec that could never be corrected was the gap: the only way to fix a wrong brief was to
cancel the card and plan a new one, which threw away its thread and its commits. These tests
pin the four things that makes true — the row moves, the log says so, another machine ends up
agreeing, and a closed card refuses.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from taskops._errors import BadRequest
from taskops.engine import build, replay
from taskops.storage import Store, all_events
from taskops.usecases import ask, edit, init, next_task, plan, sync, update


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          check=True)
    return done.stdout.strip()


@pytest.fixture
def carded(tmp_path: Path) -> tuple[Path, str]:
    init(tmp_path)
    created = plan(tmp_path, [{"title": "Parse the header", "spec": "old brief"}],
                   actor="dev:berna")["created"][0]
    return tmp_path, created["id"]


def kinds_on(root: Path, task_id: str) -> list[str]:
    with Store(root) as store:
        return [e["kind"] for e in store.events.of_task(task_id)]


def test_editing_rewrites_the_row_and_writes_one_event_per_field(
        carded: tuple[Path, str]) -> None:
    """Two fields changed, two `edited` events — a body carrying both would make replay's
    newer-wins rule all-or-nothing across fields nobody edited together."""
    root, task_id = carded
    result = edit(root, task_id, spec="the real brief", priority=0, actor="dev:berna")

    assert result["changed"] == ["spec", "priority"]
    assert result["task"]["spec"] == "the real brief"
    assert result["task"]["priority"] == 0
    assert ask(root, task_id)["task"]["spec"] == "the real brief"
    assert kinds_on(root, task_id).count("edited") == 2


def test_an_edit_that_changes_nothing_records_nothing(carded: tuple[Path, str]) -> None:
    """A no-op event would bump `updated` — the arbitrator replay uses — and so let a
    redundant edit here beat a real edit on another machine."""
    root, task_id = carded
    result = edit(root, task_id, spec="old brief", actor="dev:berna")

    assert result["changed"] == []
    assert "edited" not in kinds_on(root, task_id)


def test_editing_with_no_fields_is_refused(carded: tuple[Path, str]) -> None:
    root, task_id = carded
    with pytest.raises(BadRequest):
        edit(root, task_id, actor="dev:berna")


@pytest.mark.parametrize("status", ["done", "cancelled"])
def test_a_closed_card_refuses_to_be_rewritten(carded: tuple[Path, str], status: str) -> None:
    """The log is the record of what was delivered. Rewriting the spec of finished work
    rewrites that record, so the door is shut and the message names the way through."""
    root, task_id = carded
    if status == "done":
        next_task(root, actor="dev:berna")          # `done` needs the lease the machine demands
    update(root, task_id, actor="dev:berna", status=status, comment="Not needed.",
           no_code=True)
    assert ask(root, task_id)["task"]["status"] == status

    with pytest.raises(BadRequest, match="closed cards are history"):
        edit(root, task_id, spec="too late", actor="dev:berna")


def test_an_older_edit_does_not_clobber_a_newer_local_one(carded: tuple[Path, str]) -> None:
    """Newer-wins, from the same arbitrator `_status` uses. Without it, importing a log
    that happened to contain an old edit would silently undo a correction made since."""
    root, task_id = carded
    edit(root, task_id, spec="the newest brief", actor="dev:berna")
    stale = build(task=task_id, actor="dev:ana", kind="edited", ts=1.0,
                  body={"field": "spec", "from": "old brief", "to": "a stale brief"})

    with Store(root) as store:
        assert replay.apply(store, [stale]) == 0
    assert ask(root, task_id)["task"]["spec"] == "the newest brief"


def test_an_edit_travels_to_another_clone_and_both_converge(tmp_path: Path) -> None:
    """The point of an event log: Ana fixes the brief, Berna's board shows the fix.

    Through a real bare remote rather than by copying rows, because the whole path — export,
    git, import, replay — is what was broken when replay knew nothing about a kind.
    """
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "--initial-branch=main", str(origin))
    ana, berna = tmp_path / "ana", tmp_path / "berna"
    for who, email in ((ana, "ana@example.com"), (berna, "berna@example.com")):
        git(tmp_path, "clone", "-q", str(origin), str(who))
        git(who, "config", "user.email", email)
        git(who, "config", "user.name", who.name)
        init(who)

    task_id = plan(ana, [{"title": "Parse the header", "spec": "old brief"}],
                   actor="dev:ana")["created"][0]["id"]
    sync(ana)
    git(ana, "add", "-A")
    git(ana, "commit", "-q", "-m", "plan the work")
    git(ana, "push", "-q", "origin", "main")

    git(berna, "fetch", "-q", "origin")
    git(berna, "reset", "-q", "--hard", "origin/main")
    sync(berna)
    assert ask(berna, task_id)["task"]["spec"] == "old brief"

    edit(ana, task_id, title="Parse the header, with continuations", spec="the real brief",
         priority=0, actor="dev:ana")
    sync(ana)
    git(ana, "add", "-A")
    git(ana, "commit", "-q", "-m", "fix the brief")
    git(ana, "push", "-q", "origin", "main")

    git(berna, "fetch", "-q", "origin")
    git(berna, "reset", "-q", "--hard", "origin/main")
    report = sync(berna)

    assert report.applied >= 3, "three fields changed; three events should have landed"
    theirs, mine = ask(ana, task_id)["task"], ask(berna, task_id)["task"]
    assert mine["spec"] == theirs["spec"] == "the real brief"
    assert mine["title"] == theirs["title"] == "Parse the header, with continuations"
    assert mine["priority"] == theirs["priority"] == 0
    assert [e["kind"] for e in all_events(berna)].count("edited") == 3
