"""`taskops_capture` — one card for work nobody planned, claimed in the same call.

The reason this exists is a REFUSAL: the commit guard stops an agent that holds no card, and
before this the only way out was a three-call dance through `plan`. So the assertions are about
the loop closing — create, hold, and know which branch to commit on — and about the one thing
that must not happen: a lease minted for somebody who is not running.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskops.usecases import acceptance_for, capture, check_commit
from taskops.usecases.ask import ask


def test_a_captured_card_is_held_and_names_its_branch(root: Path) -> None:
    """The whole point in one call: the card exists, it is mine, and the reply says where to
    commit. An agent that had to look the branch up afterwards would be back to two calls."""
    made = capture(root, "fix the timeout", spec="DONE = the retry test passes",
                   actor="agent:ana/w1")
    assert made["task"]["title"] == "fix the timeout"
    claim = made["claim"]
    assert claim is not None
    assert claim["view"]["task"]["id"] == made["task"]["id"]
    assert made["task"]["id"] in claim["branch"]


def test_the_commit_the_guard_refused_is_allowed_once_captured(root: Path) -> None:
    """End to end against the real guard, because this tool's whole justification is that it
    is the way OUT of that refusal. A version that created a card the guard still rejected
    would pass every unit test and help nobody."""
    before = check_commit(root, "found a bug", actor="agent:ana/w1")
    assert not before.allowed
    assert "taskops_capture" in before.reason

    made = capture(root, "fix the bug I found", actor="agent:ana/w1")
    task = made["task"]["id"]
    verdict = check_commit(root, f"found a bug\n\nTask: {task}", actor="agent:ana/w1")
    assert verdict.allowed
    assert verdict.task == task


def test_assigning_it_to_somebody_else_never_mints_them_a_lease(root: Path) -> None:
    """A lease belongs to a process that is alive and heartbeating. One minted for an agent
    that is not running lapses fifteen minutes later with nobody watching, and the board spends
    that time claiming the work is in hand — the exact lie leases exist to prevent."""
    made = capture(root, "read the prod logs", assign="agent:ana/w2", actor="agent:ana/w1")
    assert made["claim"] is None
    assert made["assigned"] == "agent:ana/w2"
    card = ask(root, made["task"]["id"])
    assert card["task"]["status"] == "ready", "an assigned card stays pickable"


def test_the_assignment_reaches_the_other_agent(root: Path) -> None:
    """Assignment is a MENTION, so it lands in an inbox rather than in a field only the board
    reads. The card being pickable is only fair if the person it is meant for is told."""
    made = capture(root, "read the prod logs", assign="agent:ana/w2", actor="agent:ana/w1")
    card = ask(root, made["task"]["id"])
    assert any("agent:ana/w2" in event["body"].get("text", "")
               or "agent:ana/w2" in str(event["body"].get("mentions", ""))
               for event in card["thread"])


def test_recording_work_for_later_does_not_claim_it(root: Path) -> None:
    """`claim=False` is the honest case the default would get wrong: a card written down
    because it must not be forgotten, by somebody who is about to keep doing something else."""
    made = capture(root, "someday: split the parser", claim=False, actor="agent:ana/w1")
    assert made["claim"] is None
    assert made["assigned"] == ""
    assert ask(root, made["task"]["id"])["task"]["status"] == "ready"


def test_acceptance_criteria_survive_the_shortcut(root: Path) -> None:
    """Capture is the fast door, not a door around the rules: a card made this way promises
    the same checkable things, or `done` would be weaker for exactly the work nobody planned."""
    made = capture(root, "fix the timeout", actor="agent:ana/w1",
                   acceptance="WHEN the request times out THE SYSTEM SHALL retry once")
    assert acceptance_for(root, made["task"]["id"])["criteria"] == [
        "WHEN the request times out THE SYSTEM SHALL retry once"]


def test_a_card_with_no_title_is_refused(root: Path) -> None:
    with pytest.raises(Exception, match="title"):
        capture(root, "", actor="agent:ana/w1")
