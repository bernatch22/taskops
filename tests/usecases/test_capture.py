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
    that time claiming the work is in hand — the exact lie leases exist to prevent.

    Assignment is not a lease: the card is theirs and still unclaimed, waiting for them to run.
    """
    made = capture(root, "read the prod logs", assign="agent:ana/w2", actor="agent:ana/w1")
    assert made["claim"] is None
    assert made["assigned"] == "agent:ana/w2"
    card = ask(root, made["task"]["id"])
    assert card["task"]["status"] == "ready", "an assigned card is not a claimed one"
    assert card["lease"] is None


def test_assigning_it_makes_it_invisible_to_a_third_agent(root: Path) -> None:
    """THE repair. `capture(assign=...)` used to leave only a mention, so the card stayed in
    the open pool and the next agent to call `next` could take it out from under the person it
    had just been given to — while `dispatch`, using the same word, hid it from everybody.
    One meaning of "assign", and this is it."""
    from taskops.usecases import next_task

    made = capture(root, "read the prod logs", assign="agent:ana/w2", actor="agent:ana/w1")
    other = next_task(root, actor="agent:ana/intruder", task=made["task"]["id"])
    assert other["claim"] is None
    assert "agent:ana/w2" in other["reason"], "the reason must name who it belongs to"


def test_the_assignment_reaches_the_other_agent(root: Path) -> None:
    """The field the board reads is not a notification: the person it was given to has to be
    TOLD, and their inbox is where they look. So the mention survives the repair."""
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
