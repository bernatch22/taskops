"""Recovery: getting a fleet's cards back when its workers died.

Written from a real incident. Six cards in a live project sat `claimed` by six agents that had been
killed mid-run when an API balance ran out. Getting them back took six hand-written `update --status
released` calls plus a manual hunt through six worktrees for files that had never been committed —
three of them had real work in them, and nothing on the board said so.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from taskops._clock import HEARTBEAT_GRACE
from taskops.storage import Store
from taskops.usecases import ask, dispatch, init, next_task, plan, recover


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A real repository, because recovery reads worktrees with `git status`."""
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "a@b.c")
    git(tmp_path, "config", "user.name", "A")
    (tmp_path / "README.md").write_text("x\n", encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "init")
    init(tmp_path, install_git_hooks=False)
    plan(tmp_path, [{"title": "A", "spec": "a"}, {"title": "B", "spec": "b"}],
         actor="dev:berna")
    return tmp_path


def go_silent(project: Path, task_id: str) -> None:
    """Age the lease past the grace period, without waiting for it.

    Written through the SQL layer because no API can produce this state — which is the point: it is
    what a killed process leaves behind, and nothing gets a chance to tidy up.
    """
    with Store(project) as store:
        lease = store.leases.get(task_id)
        assert lease is not None
        store.db.execute("UPDATE leases SET acquired=?, expires=? WHERE task=?",
                         (lease["acquired"] - HEARTBEAT_GRACE - 60,
                          lease["expires"] + 3600, task_id))


def test_a_silent_worker_hands_its_card_back(project: Path) -> None:
    """And it does NOT wait for the lease. A person looking at a board full of SILENT rows has
    already noticed the crash; making them wait fifteen minutes for a timer to agree is a tool
    arguing with its user."""
    claimed = next_task(project, actor="agent:berna/dead")
    assert claimed["claim"] is not None
    task_id = claimed["claim"]["view"]["task"]["id"]
    go_silent(project, task_id)

    result = recover(project, actor="dev:berna")
    assert [s.task for s in result.released] == [task_id]
    assert ask(project, task_id)["task"]["status"] == "ready"
    assert ask(project, task_id)["lease"] is None


def test_recovery_clears_the_assignment_too(project: Path) -> None:
    """A card handed back still assigned to a dead worker is a card NOBODY can pick up — the
    scheduler hides it from everyone else, and its owner is gone."""
    prepared = dispatch(project, count=1, actor="dev:berna")
    task_id = prepared.launched[0].task
    next_task(project, actor=prepared.launched[0].actor, task=task_id)
    go_silent(project, task_id)

    recover(project, actor="dev:berna")
    assert ask(project, task_id)["task"]["assignee"] == ""

    taken = next_task(project, actor="agent:ana/other", task=task_id)
    assert taken["claim"] is not None, "the recovered card is still not claimable"


def test_a_live_worker_is_left_alone_and_named(project: Path) -> None:
    """Recovery must not steal a card from an agent that is working. Naming the survivors matters:
    a recovery that quietly left two cards claimed is one somebody has to check by hand anyway."""
    claimed = next_task(project, actor="agent:berna/working")
    assert claimed["claim"] is not None

    result = recover(project, actor="dev:berna")
    assert result.released == []
    assert any("agent:berna/working" in entry for entry in result.alive)


def test_force_releases_even_a_live_worker(project: Path) -> None:
    """For the case where a fleet is alive and WRONG — chasing a bad spec, say."""
    next_task(project, actor="agent:berna/working")
    result = recover(project, actor="dev:berna", force=True)
    assert len(result.released) == 1


def test_uncommitted_work_is_found_and_written_on_the_card(project: Path) -> None:
    """THE part that nearly cost real work.

    A killed agent writes before it commits, so what survives is untracked files in a worktree two
    levels down. Recovery names the PATH in the card's thread — "partial work exists" sends the next
    agent looking, a path sends it reading.
    """
    prepared = dispatch(project, count=1, actor="dev:berna")
    worker = prepared.launched[0]
    next_task(project, actor=worker.actor, task=worker.task)
    (worker.tree / "half_done.py").write_text("# started, never committed\n", encoding="utf-8")
    go_silent(project, worker.task)

    result = recover(project, actor="dev:berna")
    assert result.released[0].leftovers == ["half_done.py"]

    thread = " ".join(str(e["body"].get("text", "")) for e in ask(project, worker.task)["thread"])
    assert "half_done.py" in thread, "the leftovers are not on the card"
    assert str(worker.tree) in thread, "the thread must name the path, not just the fact"
    assert (worker.tree / "half_done.py").is_file(), "recovery deleted the work"


def test_committed_work_is_reported_as_safe(project: Path) -> None:
    """Commits survive in git, and the card should say so — otherwise the next agent cannot tell
    whether it is resuming or starting over."""
    claimed = next_task(project, actor="agent:berna/dead")
    assert claimed["claim"] is not None
    task_id = claimed["claim"]["view"]["task"]["id"]
    branch = claimed["claim"]["branch"]

    git(project, "switch", "-q", "-c", branch)
    (project / "done.py").write_text("x\n", encoding="utf-8")
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", f"work\n\nTask: {task_id}")
    from taskops.usecases import ingest_commit

    ingest_commit(project, actor="agent:berna/dead")
    go_silent(project, task_id)

    result = recover(project, actor="dev:berna")
    assert result.released[0].commits == 1
    thread = " ".join(str(e["body"].get("text", "")) for e in ask(project, task_id)["thread"])
    assert "safe in git" in thread


def test_nothing_stuck_reads_as_good_news(project: Path) -> None:
    """An empty result is the healthy outcome, so it must not look like a failure."""
    from taskops.render import render_recover

    result = recover(project, actor="dev:berna")
    assert result.released == []
    assert "Nothing to recover" in render_recover(result)


def test_the_render_flags_the_salvage(project: Path) -> None:
    """The one line somebody has to see before they let an agent redo the work."""
    from taskops.render import render_recover

    prepared = dispatch(project, count=1, actor="dev:berna")
    worker = prepared.launched[0]
    next_task(project, actor=worker.actor, task=worker.task)
    (worker.tree / "partial.py").write_text("x\n", encoding="utf-8")
    go_silent(project, worker.task)

    text = render_recover(recover(project, actor="dev:berna"))
    assert "UNCOMMITTED work survives" in text
    assert "partial.py" in text
