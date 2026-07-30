"""The stop-time net: what a stopping session owes, and when the door lets go anyway.

The scenario that demanded it: an agent claims, commits, and simply ENDS. The board says
"somebody is working on this" about nobody, and everything the agent knew dies with the turn.
The judgement lives here, hook-free, so it is testable with a Store and a string; the block
shape is the transport's problem.
"""

from __future__ import annotations

from pathlib import Path

from taskops.usecases import next_task, plan, update
from taskops.usecases.unfinished import BLOCK_LIMIT, owed, should_block

SESSION = "sess-1"


def a_claimed_card(root: Path, actor: str = "agent:ana/api1") -> str:
    task = plan(root, [{"title": "the work", "spec": "s"}], actor="dev:ana")["created"][0]["id"]
    next_task(root, task=task, actor=actor, session=SESSION)
    return task


def test_a_half_done_card_is_owed(root: Path) -> None:
    task = a_claimed_card(root)
    rows = owed(root, SESSION)
    assert [row["task"] for row in rows] == [task]
    assert rows[0]["actor"] == "agent:ana/api1", "the exit lines need the actor to name"


def test_review_and_ready_owe_nothing(root: Path) -> None:
    """Handed over IS done, from the door's point of view: review released the lease and the
    card is somebody else's to close. Only claimed/in_progress hold the stopper."""
    task = a_claimed_card(root)
    update(root, task, status="review", comment="done, criterion met", actor="agent:ana/api1")
    assert owed(root, SESSION) == []


def test_a_dev_is_never_held_at_the_door(root: Path) -> None:
    """A person closes their terminal when they please."""
    a_claimed_card(root, actor="dev:ana")
    assert owed(root, SESSION) == []


def test_the_agent_type_narrows_to_the_one_actually_stopping(root: Path) -> None:
    """Workers run in parallel. Blocking a verifier over a WORKER's half-done card would hold
    the wrong door — the verifier cannot close what it does not hold."""
    a_claimed_card(root, actor="agent:ana/api1")
    assert owed(root, SESSION, agent_type="api"), "the worker itself is held"
    assert owed(root, SESSION, agent_type="tester") == [], "the bystander is not"


def test_another_sessions_cards_are_not_this_ones_problem(root: Path) -> None:
    a_claimed_card(root)
    assert owed(root, "some-other-session") == []


def test_the_door_lets_go_after_the_limit(root: Path) -> None:
    """An agent that has read the message twice is not going to act on a third copy — it is
    confused, out of budget, or arguing. Holding it forever trades a stale board for a trapped
    session, which is the worse failure and it would be OURS."""
    task = a_claimed_card(root)
    verdicts = [should_block(root, SESSION, task) for _ in range(BLOCK_LIMIT + 2)]
    assert verdicts == [True] * BLOCK_LIMIT + [False, False]


def test_the_count_is_per_card_and_per_session(root: Path) -> None:
    """A second card, or the same card in tomorrow's session, starts fresh — the limit exists
    to free a stuck agent, not to let every future session walk past the door unexamined."""
    task = a_claimed_card(root)
    for _ in range(BLOCK_LIMIT):
        should_block(root, SESSION, task)
    assert should_block(root, SESSION, task) is False
    assert should_block(root, "tomorrow", task) is True
    other = plan(root, [{"title": "other", "spec": "s"}], actor="dev:ana")["created"][0]["id"]
    assert should_block(root, SESSION, other) is True
