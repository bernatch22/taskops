"""The state machine, tested from literals — no database in sight.

That is the whole point of guards being pure functions of `Facts`: "a claimed task
cannot be closed without a commit" is a three-line test here instead of a fixture
with a repository, a lease and a git history in it.
"""

from __future__ import annotations

import pytest

from taskops._errors import GuardFailed, IllegalTransition
from taskops._types import STATUSES, Status
from taskops.contracts import Task
from taskops.engine.machine import TRANSITIONS, Facts, allowed_from, check_move
from tests.conftest import CLOCK


def a_task(status: Status) -> Task:
    return Task(id="tk-aaaaaa", title="t", spec="s", status=status, priority=2,
                parent=None, labels=[], files=[], created_by="dev:berna", assignee="", reviewer="",
                created=CLOCK, updated=CLOCK)


def facts(status: Status, **over: object) -> Facts:
    base: dict[str, object] = {"task": a_task(status), "actor": "agent:berna/one",
                               "has_live_lease": True, "commits": 1,
                               "open_children": 0, "no_code": False,
                               "justification": "", "unpushed": 0}
    return Facts(**{**base, **over})          # type: ignore[arg-type]


def test_the_table_covers_every_status() -> None:
    """Anti-vacuum: a status missing from the table would be silently terminal, so
    every guard test about it would pass by never running."""
    assert set(TRANSITIONS) == set(STATUSES)


def test_done_is_terminal() -> None:
    """Reopening would make the log say a task finished twice. The honest record of
    "we shipped it and it was wrong" is a new task referencing the old one."""
    assert allowed_from("done") == ()
    with pytest.raises(IllegalTransition):
        check_move(facts("done"), "claimed")


def test_an_impossible_arrow_names_the_possible_ones() -> None:
    """A rejected agent must learn the shape of the machine, not guess again."""
    with pytest.raises(IllegalTransition) as caught:
        check_move(facts("backlog"), "done")
    message = str(caught.value)
    assert "ready" in message and "cancelled" in message


def test_working_on_a_task_requires_a_live_lease() -> None:
    with pytest.raises(GuardFailed) as caught:
        check_move(facts("claimed", has_live_lease=False), "review")
    assert "lease" in str(caught.value)


def test_closing_requires_a_commit() -> None:
    """THE guard that makes the board trustworthy: without it, `done` means only
    that an agent said so — which is what reading a board instead of the diff is
    meant to avoid."""
    with pytest.raises(GuardFailed) as caught:
        check_move(facts("claimed", commits=0), "done")
    assert "no commit bound" in str(caught.value)


def test_no_code_closes_a_task_only_with_a_justification() -> None:
    """An unexplained exemption is indistinguishable from a shortcut."""
    with pytest.raises(GuardFailed) as caught:
        check_move(facts("claimed", commits=0, no_code=True), "done")
    assert "comment" in str(caught.value)
    check_move(facts("claimed", commits=0, no_code=True,
                     justification="Decided to keep the existing scheme; see thread."),
               "done")


def test_an_epic_is_done_when_its_children_are() -> None:
    with pytest.raises(GuardFailed) as caught:
        check_move(facts("review", open_children=2), "done")
    assert "open subtask" in str(caught.value)


def test_the_children_check_comes_before_the_commit_check() -> None:
    """Order matters for the AGENT, not for correctness.

    Told to write a commit for an epic whose subtasks are unfinished, an agent goes
    and does the wrong work. Told about the subtasks, it does the right one.
    """
    with pytest.raises(GuardFailed) as caught:
        check_move(facts("claimed", commits=0, open_children=1), "done")
    assert "open subtask" in str(caught.value)


def test_releasing_is_always_allowed() -> None:
    """Handing work back must never be harder than abandoning it.

    A guard here would make waiting for the lease to lapse the easier move, and a
    lapsed lease carries none of the context a release comment does.
    """
    for status in ("claimed", "claimed"):
        check_move(facts(status, has_live_lease=False, commits=0), "ready")


def test_unpushed_work_does_not_block_closing() -> None:
    """It is RECORDED, not enforced. Pushing is not always the closer's job — a task can finish on
    a branch somebody else lands — and a repository with no remote at all would otherwise be unable
    to close anything, which is the most common way taskops is first tried."""
    check_move(facts("claimed", unpushed=3), "done")


def test_cancelling_is_always_allowed_from_an_open_status() -> None:
    """A human deciding a task should not happen cannot be blocked by a guard about
    evidence — there is deliberately no work to show."""
    for status in ("backlog", "ready", "claimed", "claimed", "blocked", "review"):
        check_move(facts(status, has_live_lease=False, commits=0), "cancelled")


def test_a_worker_may_not_close_the_review_it_asked_for() -> None:
    """The handoff rule, from literals: `review` means nothing if the agent that asked for it
    is also the one that grants it."""
    with pytest.raises(GuardFailed) as caught:
        check_move(facts("review", entered_review_by="agent:berna/one"), "done")
    said = str(caught.value)
    assert "another's to close" in said
    assert "verifier" in said, "a refusal that names no way out is a dead end"


def test_a_different_agent_closes_the_same_review() -> None:
    check_move(facts("review", entered_review_by="agent:berna/two"), "done")


def test_a_dev_closes_a_review_whoever_opened_it() -> None:
    """A human reading the diff IS the review. The rule is about agents grading themselves."""
    check_move(facts("review", actor="dev:berna", entered_review_by="dev:berna"), "done")


def test_a_card_that_never_entered_review_is_untouched() -> None:
    """Compatibility, stated as a test: the fact defaults to empty, so every card written
    before this rule existed closes on exactly the guards it always had."""
    check_move(facts("claimed"), "done")


def test_the_handoff_is_refused_before_the_commit_check() -> None:
    """Order, for the agent again: telling a worker to go write a commit for a card it is not
    allowed to close at all would send it to do work that gets refused anyway."""
    with pytest.raises(GuardFailed) as caught:
        check_move(facts("review", commits=0, entered_review_by="agent:berna/one"), "done")
    assert "another's to close" in str(caught.value)


def test_a_rejection_with_no_findings_is_refused() -> None:
    """`review → ready` is the REJECTION, and it is the one arrow that must carry text.

    The rule is not new — `tasks reject` has demanded `-m` since it existed. It lived in
    ARGPARSE, so it held for a person on a terminal and not for the verifier, which is an agent
    calling `taskops_update status=ready` through MCP. Every rejection an agent ever made
    arrived blank: the worker got its card back reading "not good enough" and guessed, which is
    how a card goes round twice for no reason.

    Here rather than in the CLI because the state machine has exactly one home. A rule a
    transport enforces is a rule the other two do not, and the one that skips it is always the
    one doing the work.
    """
    with pytest.raises(GuardFailed) as refused:
        check_move(facts("review"), "ready")
    assert "no findings" in str(refused.value)
    assert "a test name" in str(refused.value), "and it says what would be enough"


def test_a_rejection_that_says_what_failed_is_allowed() -> None:
    check_move(facts("review", comment="FAILS: the empty case raises — pytest -k empty"), "ready")


def test_whitespace_is_not_a_finding() -> None:
    """A space satisfies "not empty" and tells the worker exactly as much as nothing did."""
    with pytest.raises(GuardFailed):
        check_move(facts("review", comment="   \n  "), "ready")


def test_handing_work_back_from_a_WORKING_status_still_needs_no_reason() -> None:
    """The release path stays unguarded, deliberately: an agent out of depth must always be
    able to hand work back, and a guard there makes waiting for the lease to lapse the easier
    move — which loses the context a release comment would have carried.

    Only the arrow OUT OF REVIEW is a rejection. `claimed → ready` and `blocked → ready` are
    somebody giving up, and giving up must never be harder than abandoning.
    """
    check_move(facts("claimed"), "ready")
    check_move(facts("blocked"), "ready")
