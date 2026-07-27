"""The claim, the dependency graph, and the crash-recovery path.

The concurrency test uses REAL THREADS with REAL connections, because that is the
only version that can fail: a test that calls `claim` twice in one thread passes
against a broken implementation, since the race it is meant to catch needs two
transactions open at once.
"""

from __future__ import annotations

import threading
from pathlib import Path

from taskops._clock import LEASE_TTL
from taskops.contracts import Task
from taskops.engine import scheduler
from taskops.storage import Store
from tests.conftest import CLOCK


def make(store: Store, task_id: str, **over: object) -> Task:
    base: dict[str, object] = {"id": task_id, "title": f"task {task_id}", "spec": "s",
                               "status": "ready", "priority": 2, "parent": None,
                               "labels": [], "files": [], "created_by": "dev:berna",
                               "created": CLOCK, "updated": CLOCK}
    task = Task(**{**base, **over})           # type: ignore[typeddict-item]
    store.tasks.insert(task)
    return task


def test_a_task_with_an_open_dependency_is_not_ready(store: Store) -> None:
    make(store, "tk-first", status="backlog")
    make(store, "tk-second", status="backlog")
    store.deps.add("tk-first", "tk-second")
    scheduler.unblock(store, at=CLOCK)
    assert [t["id"] for t in scheduler.ready_tasks(store)] == ["tk-first"]


def test_closing_a_dependency_unblocks_its_dependents(store: Store) -> None:
    """The auto-unblock. Nothing polls: `unblock` runs on the write path."""
    make(store, "tk-first", status="in_progress")
    make(store, "tk-second", status="backlog")
    store.deps.add("tk-first", "tk-second")
    scheduler.unblock(store, at=CLOCK)
    assert scheduler.ready_tasks(store) == []

    store.tasks.set_status("tk-first", "done", when=CLOCK)
    assert scheduler.unblock(store, at=CLOCK) == ["tk-second"]
    assert [t["id"] for t in scheduler.ready_tasks(store)] == ["tk-second"]


def test_a_ready_task_that_gains_a_dependency_is_demoted(store: Store) -> None:
    """A discovery made mid-flight must not leave work that only LOOKS pickable."""
    make(store, "tk-blocker", status="in_progress")
    make(store, "tk-target", status="ready")
    store.deps.add("tk-blocker", "tk-target")
    scheduler.unblock(store, at=CLOCK)
    assert store.tasks.need("tk-target")["status"] == "backlog"


def test_a_cancelled_dependency_stops_blocking(store: Store) -> None:
    """A task nobody will ever do must not hold its dependents hostage forever."""
    make(store, "tk-abandoned", status="cancelled")
    make(store, "tk-waiting", status="backlog")
    store.deps.add("tk-abandoned", "tk-waiting")
    assert scheduler.unblock(store, at=CLOCK) == ["tk-waiting"]


def test_priority_orders_the_ready_set(store: Store) -> None:
    make(store, "tk-later", priority=3)
    make(store, "tk-now", priority=0)
    assert [t["id"] for t in scheduler.ready_tasks(store)] == ["tk-now", "tk-later"]


def test_a_file_another_agent_is_editing_sorts_last(store: Store) -> None:
    """Anti-collision, and it OUTRANKS priority.

    An urgent task handed to a second agent in the same file is not urgent work, it
    is two agents about to undo each other.
    """
    busy = make(store, "tk-busy", status="in_progress", files=["a.py"])
    make(store, "tk-urgent", priority=0, files=["a.py"])
    make(store, "tk-quiet", priority=3, files=["b.py"])
    scheduler.claim(store, busy, actor="agent:ana/one", at=CLOCK)
    order = [t["id"] for t in scheduler.ready_tasks(store)]
    assert order == ["tk-quiet", "tk-urgent"]


def test_labels_restrict_the_pool(store: Store) -> None:
    make(store, "tk-ui", labels=["frontend"])
    make(store, "tk-db", labels=["storage"])
    picked = scheduler.ready_tasks(store, labels=("frontend",))
    assert [t["id"] for t in picked] == ["tk-ui"]


def test_only_one_of_two_claims_wins(store: Store) -> None:
    task = make(store, "tk-contested")
    first = scheduler.claim(store, task, actor="agent:berna/one", at=CLOCK)
    second = scheduler.claim(store, task, actor="agent:ana/two", at=CLOCK)
    assert first is not None
    assert second is None


def test_an_expired_lease_returns_the_task_to_ready(store: Store) -> None:
    """The crash-recovery path, in microseconds instead of fifteen real minutes —
    which is the entire reason `now` is a parameter everywhere."""
    task = make(store, "tk-abandoned")
    scheduler.claim(store, task, actor="agent:berna/gone", at=CLOCK)
    store.tasks.set_status(task["id"], "in_progress", when=CLOCK)

    later = CLOCK + LEASE_TTL + 1
    assert scheduler.sweep_dead(store, at=later) == ["tk-abandoned"]
    assert store.tasks.need("tk-abandoned")["status"] == "ready"
    assert scheduler.claim(store, task, actor="agent:ana/two", at=later) is not None


def test_the_branch_name_is_derived_from_the_task(store: Store) -> None:
    """The guard's pattern and this string are one contract — an agent inventing its
    own branch would be denied its own commits with no clue why."""
    task = make(store, "tk-abc123", title="Fix the WAL pragma!! (urgent)")
    assert scheduler.branch_for(task) == "tk/tk-abc123/fix-the-wal-pragma-urgent"


def test_fifty_threads_claiming_one_task_produce_one_winner(root: Path) -> None:
    """The race, with real threads and real connections.

    Each thread opens its OWN Store, because that is the deployment: every MCP
    session is a separate process with its own connection. A shared connection would
    serialise the calls and test nothing.
    """
    with Store(root) as setup:
        make(setup, "tk-hot")

    wins: list[str] = []
    lock = threading.Lock()

    def attempt(n: int) -> None:
        with Store(root, check_same_thread=False) as store:
            store.claiming()
            task = store.tasks.need("tk-hot")
            got = scheduler.claim(store, task, actor=f"agent:berna/w{n}", at=CLOCK)
            if got is not None:
                with lock:
                    wins.append(got["actor"])

    threads = [threading.Thread(target=attempt, args=(n,)) for n in range(50)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(wins) == 1, f"{len(wins)} agents claimed one task: {wins}"
