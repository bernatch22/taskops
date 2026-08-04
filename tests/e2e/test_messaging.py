"""Two agents talking, and two clones converging. The plan's two central claims.

Neither is testable from a unit: the first needs two actors and the delivery table's
"has this one been shown" bookkeeping, and the second needs two real git repositories
exchanging a file through a remote.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from taskops.usecases import ask, init, next_task, plan, sync, update
from taskops.usecases.milestone import open_chapter
from taskops.usecases.session import brief, inbox


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          check=True)
    return done.stdout.strip()


@pytest.fixture
def shared(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "berna@example.com")
    git(tmp_path, "config", "user.name", "Berna")
    # Every card belongs to a chapter: the fixture opens one so the test can be about its own
    # subject rather than about that.
    init(tmp_path)
    open_chapter(tmp_path, "the chapter these tests plan into",
                 actor="dev:berna")
    return tmp_path


def test_a_mention_reaches_the_other_agents_inbox(shared: Path) -> None:
    """The agent-to-agent channel. Delivery is per (actor, event), so it cannot be skipped
    by a cursor that moved past a message which arrived late."""
    planned = plan(shared, [{"title": "Refactor the parser", "spec": "x",
                             "files": ["parser.py"]}])
    task_id = planned["created"][0]["id"]

    update(shared, task_id, actor="agent:berna/one",
           comment="I am rewriting the tokenizer — hold off on parser.py.",
           mentions=("agent:ana/two",))

    theirs = inbox(shared, actor="agent:ana/two")
    assert len(theirs["messages"]) == 1
    assert "tokenizer" in theirs["messages"][0]["body"]["text"]
    assert theirs["tasks"] == [task_id]


def test_a_message_is_delivered_exactly_once(shared: Path) -> None:
    """Read twice must not deliver twice: these get INJECTED into a session, and a message
    that reappears on every tool call would make an agent answer it repeatedly."""
    planned = plan(shared, [{"title": "T", "spec": "x"}])
    update(shared, planned["created"][0]["id"], actor="agent:berna/one",
           comment="ping", mentions=("agent:ana/two",))

    assert len(inbox(shared, actor="agent:ana/two")["messages"]) == 1
    assert inbox(shared, actor="agent:ana/two")["messages"] == []


def test_a_mention_does_not_reach_anybody_else(shared: Path) -> None:
    """Substring safety: `dev:an` must not match `dev:ana`.

    The pending query is a LIKE over the JSON body, so the quoting is what makes this
    correct — the body stores `"agent:ana/two"` with its quotes.
    """
    planned = plan(shared, [{"title": "T", "spec": "x"}])
    update(shared, planned["created"][0]["id"], actor="agent:berna/one",
           comment="ping", mentions=("agent:ana/two",))

    assert inbox(shared, actor="agent:ana/tw")["messages"] == []
    assert inbox(shared, actor="agent:berna/one")["messages"] == []


def test_the_claim_carries_the_inbox(shared: Path) -> None:
    """An agent that just took work is the most likely to have been messaged about it, so
    the messages ride along rather than costing another call."""
    planned = plan(shared, [{"title": "Shared file work", "spec": "x"}])
    task_id = planned["created"][0]["id"]
    update(shared, task_id, actor="dev:berna", comment="read the ADR first",
           mentions=("agent:berna/one",))

    claimed = next_task(shared, actor="agent:berna/one")
    assert claimed["claim"] is not None
    assert len(claimed["claim"]["inbox"]["messages"]) == 1


def test_the_brief_tells_a_session_what_it_holds(shared: Path) -> None:
    """The SessionStart read. A resumed session must find its own claims."""
    planned = plan(shared, [{"title": "Held work", "spec": "x"}])
    next_task(shared, actor="agent:berna/one", session="sess-1")

    resumed = brief(shared, session="sess-2", actor="agent:berna/one")
    assert [lease["task"] for lease in resumed.held] == [planned["created"][0]["id"]]


def test_the_collision_warning_names_the_other_task(shared: Path) -> None:
    """The one thing that prevents a merge conflict instead of reporting it."""
    planned = plan(shared, [
        {"title": "Rewrite the tokenizer", "spec": "x", "files": ["parser.py"]},
        {"title": "Add parser tests", "spec": "y", "files": ["parser.py"]},
    ])
    first, second = (t["id"] for t in planned["created"])
    next_task(shared, actor="agent:berna/one", task=first)

    view = ask(shared, second)
    assert [t["id"] for t in view["neighbours"]] == [first]


def test_two_clones_converge_through_git(tmp_path: Path) -> None:
    """Multi-developer sync with NO server, asserted on the BOARD.

    The earlier version of this test checked that the events arrived and that the task id appeared
    in the log file. Both were true and the feature was still broken: importing events created no
    tasks, so a teammate's `git pull` left them looking at an empty board. That is why every
    assertion here is about what somebody would actually SEE — the tasks, their specs, and the
    dependency graph — and none of them is about the log.
    """
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "--initial-branch=main", str(origin))

    ana, berna = tmp_path / "ana", tmp_path / "berna"
    for who, email in ((ana, "ana@example.com"), (berna, "berna@example.com")):
        git(tmp_path, "clone", "-q", str(origin), str(who))
        git(who, "config", "user.email", email)
        git(who, "config", "user.name", who.name)
        init(who)
        open_chapter(who, "the chapter these tests plan into",
                     actor="dev:berna")

    planned = plan(ana, [
        {"title": "Ana's foundation", "spec": "The full brief, which must travel.",
         "files": ["api/core.py"], "priority": 0, "labels": ["api"]},
        {"title": "Ana's follow-up", "spec": "Depends on the first.", "after": [0]},
    ], actor="dev:ana")
    first, second = (task["id"] for task in planned["created"])
    sync(ana)
    git(ana, "add", "-A")
    git(ana, "commit", "-q", "-m", "plan")
    git(ana, "push", "-q", "origin", "main")

    git(berna, "fetch", "-q", "origin")
    git(berna, "reset", "-q", "--hard", "origin/main")
    report = sync(berna)
    assert report.imported >= 2, "berna's clone did not import ana's events"
    assert report.applied >= 2, "the events arrived but created no tasks"

    # Ana's task, on Berna's board, with everything an agent needs to work on it.
    landed = ask(berna, first)["task"]
    assert landed["title"] == "Ana's foundation"
    assert landed["spec"] == "The full brief, which must travel."
    assert landed["files"] == ["api/core.py"]
    assert landed["priority"] == 0
    assert landed["labels"] == ["api"]
    assert landed["created_by"] == "dev:ana"

    # And the DAG, which is what stops Berna's agents starting the wrong one first.
    assert [t["id"] for t in ask(berna, second)["blocked_by"]] == [first]
    assert ask(berna, first)["task"]["status"] == "ready"
    assert ask(berna, second)["task"]["status"] == "backlog"


def test_a_status_change_travels_and_unblocks_on_the_other_side(tmp_path: Path) -> None:
    """Ana finishes something; Berna's queue changes. The point of sharing a list at all."""
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "--initial-branch=main", str(origin))
    ana, berna = tmp_path / "ana", tmp_path / "berna"
    for who, email in ((ana, "ana@example.com"), (berna, "berna@example.com")):
        git(tmp_path, "clone", "-q", str(origin), str(who))
        git(who, "config", "user.email", email)
        git(who, "config", "user.name", who.name)
        init(who)
        open_chapter(who, "the chapter these tests plan into",
                     actor="dev:berna")

    planned = plan(ana, [{"title": "Blocker", "spec": "x"},
                         {"title": "Waiter", "spec": "y", "after": [0]}], actor="dev:ana")
    first, second = (task["id"] for task in planned["created"])
    update(ana, first, actor="dev:ana", status="cancelled", comment="Not needed after all.")
    sync(ana)
    git(ana, "add", "-A")
    git(ana, "commit", "-q", "-m", "cancel the blocker")
    git(ana, "push", "-q", "origin", "main")

    git(berna, "fetch", "-q", "origin")
    git(berna, "reset", "-q", "--hard", "origin/main")
    report = sync(berna)

    assert ask(berna, first)["task"]["status"] == "cancelled"
    # A cancelled dependency stops blocking, so `sync` must hand Berna a pickable task.
    #
    # This assertion caught a real regression the moment `unblock` started recording. Ana's own
    # sync derived the promotion first and now LOGS it, so it reaches Berna as a replayed event
    # and Berna's local re-derivation has nothing left to do. Reading `unblock`'s return meant
    # `unblocked` came back empty while the queue really had changed — the report going silent
    # about the one thing sync exists to announce. So it is a before/after diff of the pickable
    # set instead, which cannot tell the two routes apart. See `scheduler.pickable`.
    assert second in report.unblocked
    assert ask(berna, second)["task"]["status"] == "ready"


def test_replaying_the_same_log_twice_changes_nothing(tmp_path: Path) -> None:
    """Idempotence at the REPLAY layer, not just at the event table.

    `git pull` can deliver the same log again, and `taskops sync` is documented as safe to run in a
    loop — so a second pass must not duplicate a task or resurrect a status somebody moved on from.
    """
    from taskops.usecases import rebuild

    init(tmp_path)
    open_chapter(tmp_path, "the chapter these tests plan into",
                 actor="dev:berna")
    planned = plan(tmp_path, [{"title": "Once", "spec": "x"}], actor="dev:berna")
    sync(tmp_path)
    before = ask(tmp_path, planned["created"][0]["id"])["task"]

    first = rebuild(tmp_path)
    second = rebuild(tmp_path)
    assert first.applied == 0 and second.applied == 0, "a replay changed already-correct state"
    assert ask(tmp_path, planned["created"][0]["id"])["task"] == before


def test_importing_the_same_log_twice_changes_nothing(shared: Path) -> None:
    """Idempotence, which is what makes a `git pull` safe to run in a loop.

    Content-hash ids: the second import is a primary-key no-op rather than a duplicate
    comment in somebody's inbox.
    """
    plan(shared, [{"title": "T", "spec": "x"}])
    sync(shared)
    first = sync(shared)
    second = sync(shared)
    assert first.imported == 0 and second.imported == 0
