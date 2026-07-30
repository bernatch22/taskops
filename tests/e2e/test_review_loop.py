"""The handoff, driven through the real use cases against a real repository.

The rule under test is one sentence: a worker ends at `review`, and somebody ELSE turns that
into `done`. It is tested end to end rather than only from `Facts` literals because the
interesting half is the DERIVATION — nothing stores "who asked for the review", so the answer
has to come back out of the event log through `usecases._facts`, and a unit test that hands the
guard the answer directly would prove nothing about where the answer comes from.

The last two tests are the compatibility half, and they are the ones worth keeping honest: a
guard that also refused the flows every existing card used would be a rule nobody could adopt.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from taskops._errors import GuardFailed
from taskops.usecases import init, next_task, plan, update

WORKER = "agent:berna/one"
VERIFIER = "agent:berna/verifier"
DEV = "dev:berna"

CRITERIA = ["WHEN a worker closes its own review THE SYSTEM SHALL refuse"]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "b@example.com"),
                 ("config", "user.name", "Berna")):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    init(tmp_path)
    return tmp_path


def a_card(repo: Path, *, criteria: list[str] | None = None) -> str:
    """One planned card, claimed by WORKER — the state every test here starts from."""
    plan(repo, [{"title": "Ship it", "spec": "x",
                 "acceptance": criteria if criteria is not None else CRITERIA}], actor=DEV)
    claimed = next_task(repo, actor=WORKER, session="s-1")["claim"]
    if claimed is None:
        raise AssertionError("the card was not claimable — the fixture is wrong, not the guard")
    return str(claimed["view"]["task"]["id"])


def closes(repo: Path, task: str, actor: str) -> None:
    """A close that satisfies every OTHER closing rule, so only the handoff can refuse it.

    `no_code` with a justification stands in for the commit and `evidence` for the criteria:
    the point of these tests is WHO closes, and a failure caused by a missing commit would look
    identical from the outside while proving something else entirely.
    """
    update(repo, task, actor=actor, status="done", comment="research card",
           no_code=True, evidence="the criterion: verified by hand")


def test_the_worker_that_asked_for_the_review_may_not_close_it(repo: Path) -> None:
    """THE rule. Before this guard, the worker's own `done` was self-certification."""
    task = a_card(repo)
    update(repo, task, actor=WORKER, status="review", comment="criterion 1: I believe I met it")

    with pytest.raises(GuardFailed) as refused:
        closes(repo, task, WORKER)
    said = str(refused.value)
    assert "review is" in said and "another's to close" in said
    assert "verifier" in said, "the refusal has to name the way OUT, not just say no"


def test_another_agent_closes_it_with_evidence(repo: Path) -> None:
    """The path the refusal points at: a different actor, so the review is a review."""
    task = a_card(repo)
    update(repo, task, actor=WORKER, status="review", comment="ready")
    closes(repo, task, VERIFIER)


def test_a_dev_may_always_close_a_review(repo: Path) -> None:
    """A human reading the diff IS the review. Making a person hand their own card to an
    agent before they could close it would get the guard removed within the hour."""
    task = a_card(repo)
    update(repo, task, actor=WORKER, status="review", comment="ready")
    closes(repo, task, DEV)


def test_a_card_that_never_saw_review_closes_exactly_as_before(repo: Path) -> None:
    """Compatibility, and the reason the fact is derived from the LAST status move: every card
    written before this rule existed goes claimed -> done, by the agent that claimed it."""
    task = a_card(repo, criteria=[])
    update(repo, task, actor=WORKER, status="done", comment="trivial", no_code=True)


def test_a_card_bounced_back_goes_round_again_rather_than_closing(repo: Path) -> None:
    """A bounce does not hand the worker a shortcut. The card still carries criteria, so the
    FIX gets checked too — the worker re-claims, works, hands it over again, and the verifier
    closes. Letting it self-close after a bounce would make one rejection the price of skipping
    review entirely, which is the loophole a determined agent finds first."""
    task = a_card(repo)
    update(repo, task, actor=WORKER, status="review", comment="ready")
    update(repo, task, actor=VERIFIER, status="ready", comment="FAILS: no test asserts it")

    # Re-CLAIMED, because `review` released the lease: while it sat there nobody held it, which
    # is what let the verifier read it in the first place. Coming back to work is claiming.
    next_task(repo, task=task, actor=WORKER)
    with pytest.raises(GuardFailed, match="acceptance criteria"):
        closes(repo, task, WORKER)

    update(repo, task, actor=WORKER, status="review", comment="round 2: asserted")
    closes(repo, task, VERIFIER)
