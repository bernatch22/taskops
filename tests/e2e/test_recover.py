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


def test_recover_is_reachable_over_mcp(project: Path) -> None:
    """An ORCHESTRATOR has to be able to unstick the board from inside a session.

    It could not, and that was the miss: `recover` shipped as a CLI command only, so an agent asked to
    "reassign the stale cards" had no tool to call. Recovering a dead fleet is the other half of
    dispatching one — the half that runs when the first half went wrong.
    """
    from taskops.transports.mcp import listing, respond

    assert "taskops_recover" in {t["name"] for t in listing()}

    claimed = next_task(project, actor="agent:berna/dead")
    assert claimed["claim"] is not None
    go_silent(project, claimed["claim"]["view"]["task"]["id"])

    reply = respond({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                     "params": {"name": "taskops_recover",
                                "arguments": {"repo_path": str(project), "actor": "dev:berna"}}})
    assert reply is not None
    text = str(reply["result"]["content"][0]["text"])
    assert "isError" not in reply["result"]
    assert "recovered 1 card" in text


def test_no_dead_field_survives_in_the_field_descriptions() -> None:
    """Every description constant must be referenced by a contract.

    A leftover one is dead text nobody reads and nobody can reach — which is exactly what `SPAWN`
    became when the field was removed from the MCP surface, and it sat there looking authoritative.
    """
    from taskops.contracts import _fields, tools

    source = Path(tools.__file__).read_text(encoding="utf-8")
    unused = [name for name in _fields.__all__
              if name.isupper() and f"f.{name}" not in source]
    assert not unused, f"unreferenced description constants: {unused}"


def test_a_card_just_sent_back_keeps_its_worker(project: Path) -> None:
    """The send-back keeps the assignee precisely so only its worker retakes it. An ungraced
    orphan sweep put it straight back in the pool — the opposite of what the verifier asked
    for — and any `recover` between the bounce and the worker's next turn did it."""
    from taskops.usecases import next_task, plan, recover, update
    from taskops.usecases._handoff import hand_over

    card = plan(project, [{"title": "t", "spec": "s"}], actor="dev:ana")["created"][0]["id"]
    with Store(project) as store:
        hand_over(store, card, "agent:ana/api1", actor="dev:ana")
    next_task(project, task=card, actor="agent:ana/api1")
    update(project, card, status="review", comment="round 1", actor="agent:ana/api1")
    update(project, card, status="ready", comment="FAILS: no test", actor="agent:ana/tester")

    recover(project, actor="dev:ana")

    with Store(project) as store:
        assert store.tasks.need(card)["assignee"] == "agent:ana/api1"


def test_an_assignment_left_untouched_past_the_grace_is_freed(project: Path) -> None:
    """The rule this exists for is still enforced: an assignment nobody ever picks up hides the
    card from every other agent, so it must not hide forever. Only the WAIT changed."""
    from taskops.usecases import plan, recover
    from taskops.usecases._handoff import hand_over

    card = plan(project, [{"title": "t", "spec": "s"}], actor="dev:ana")["created"][0]["id"]
    with Store(project) as store:
        hand_over(store, card, "agent:ana/ghost", actor="dev:ana")

    recover(project, actor="dev:ana", grace=0.0)

    with Store(project) as store:
        assert store.tasks.need(card)["assignee"] == ""


def test_force_frees_it_regardless(project: Path) -> None:
    """For the case the docstring names: a fleet that is alive and wrong."""
    from taskops.usecases import plan, recover
    from taskops.usecases._handoff import hand_over

    card = plan(project, [{"title": "t", "spec": "s"}], actor="dev:ana")["created"][0]["id"]
    with Store(project) as store:
        hand_over(store, card, "agent:ana/api1", actor="dev:ana")

    recover(project, actor="dev:ana", force=True)

    with Store(project) as store:
        assert store.tasks.need(card)["assignee"] == ""
