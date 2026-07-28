"""Acceptance criteria: what a card promises, and what it takes to say it was kept.

Five failure modes earn a test, and every one of them is silent:
a criterion split in half by a comma, a warning that turned into a refusal, an old list
resurrected by a rewrite, a card with no criteria that suddenly cannot be closed, and an
escape hatch that lets a closer say nothing at all.
"""

from __future__ import annotations

from pathlib import Path

from taskops.engine import Evidence, evidenced
from taskops.storage import Store
from taskops.usecases.acceptance import (
    acceptance_for,
    check,
    criteria_in,
    criteria_of,
    set_acceptance,
)
from taskops.usecases.edit import edit
from taskops.usecases.plan import plan

WHEN = "WHEN the lease expires, THE SYSTEM SHALL return the card to the queue"
PROSE = "it should probably requeue stuff"


def test_a_criterion_is_split_on_lines_and_never_on_commas() -> None:
    """THE parsing bug this field invites. Every other list here is comma-separated, and an
    EARS line has a comma in it by construction — splitting on one turns a criterion into two
    fragments that assert nothing and read as if somebody wrote them."""
    assert criteria_in(f"{WHEN}\nWHILE offline, THE SYSTEM SHALL queue") == [
        WHEN, "WHILE offline, THE SYSTEM SHALL queue"]
    assert criteria_in([WHEN]) == [WHEN]
    assert criteria_in(None) == []


def test_prose_is_warned_about_and_kept() -> None:
    """Lax on purpose. A criterion rejected over grammar is a criterion nobody writes down,
    and a card whose criteria are prose is strictly better than a card with none."""
    result = check([WHEN, PROSE])
    assert result["criteria"] == [WHEN, PROSE], "a warned criterion was dropped"
    assert len(result["warnings"]) == 1
    assert "EARS" in result["warnings"][0]


def test_a_plan_entry_carries_its_criteria(root: Path) -> None:
    created = plan(root, [{"title": "Requeue", "spec": "x", "acceptance": [WHEN]}])["created"]
    assert acceptance_for(root, created[0]["id"])["criteria"] == [WHEN]


def test_a_card_planned_without_criteria_has_none(root: Path) -> None:
    """Compatibility, pinned: every card that predates this reads back as an empty list, not
    as a missing field and not as an error."""
    created = plan(root, [{"title": "Old card", "spec": "x"}])["created"]
    assert acceptance_for(root, created[0]["id"])["criteria"] == []


def test_a_rewrite_replaces_rather_than_accumulates(root: Path) -> None:
    """Criteria are what the card promises NOW. Merging would resurrect a promise somebody
    deliberately dropped, and the dropped one is always the one that was wrong."""
    task = plan(root, [{"title": "Requeue", "spec": "x", "acceptance": [WHEN]}])["created"][0]
    set_acceptance(root, task["id"], ["WHEN it expires THE SYSTEM SHALL email"])
    assert acceptance_for(root, task["id"])["criteria"] == [
        "WHEN it expires THE SYSTEM SHALL email"]


def test_edit_sets_criteria_on_a_card_that_had_none(root: Path) -> None:
    """The door back. A card planned before anybody thought about acceptance must be able to
    gain it without cancelling the card and losing its thread."""
    task = plan(root, [{"title": "Requeue", "spec": "x"}])["created"][0]
    assert "acceptance" in edit(root, task["id"], acceptance=[WHEN])["changed"]
    assert acceptance_for(root, task["id"])["criteria"] == [WHEN]


def test_the_criteria_of_a_card_nobody_set_are_empty(store: Store) -> None:
    """A read that cannot raise: the verifier calls it on whatever id it was handed, and a
    card it has never heard of must answer "none promised" rather than blow up mid-review."""
    assert criteria_of(store, "tk-000000") == []


def test_closing_a_card_with_criteria_demands_evidence() -> None:
    """The guard, from literals. It is the whole point of the field: without it, criteria are
    decoration an agent scrolls past on its way to setting done."""
    refusal = evidenced(Evidence(criteria=(WHEN,)))
    assert refusal is not None
    assert "evidence" in refusal and WHEN[:20] in refusal


def test_evidence_or_an_argued_waiver_both_close_it() -> None:
    """A rule with no honest exit gets bypassed by lying, so the exit exists — and it costs a
    reason, which lands in the done event where a review can find it."""
    assert evidenced(Evidence(criteria=(WHEN,), given="test_requeues_on_expiry passes")) is None
    assert evidenced(Evidence(criteria=(WHEN,), waived="the lease design changed")) is None


def test_a_card_with_no_criteria_closes_exactly_as_before() -> None:
    """The compatibility half of the guard. Every card on every existing board has no
    criteria, and this rule must be invisible to all of them."""
    assert evidenced(Evidence()) is None
    assert evidenced(None) is None
