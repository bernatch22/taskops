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
from taskops.usecases import ask, init, next_task, plan, update

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


def test_peer_review_refuses_the_author_s_own_developer(repo: Path) -> None:
    """The hole found in a live two-developer run, and the same bug that was called critical
    once already arriving through a different door: `_handed_on` compares ACTOR IDS, so
    `dev:dev2` closing what `agent:dev2/w1` handed over is two different strings and passes —
    while being, in every sense that matters, the author closing their own work. It happened to
    two real cards, WHILE independent verifiers were still running on them."""
    from taskops.usecases import context_state

    context_state(repo, "decision", "reviewer: peer", actor=DEV)
    card = plan(repo, [{"title": "t", "spec": "s", "acceptance": CRITERIA}],
                actor=DEV)["created"][0]["id"]
    next_task(repo, task=card, actor="agent:berna/w1")
    update(repo, card, status="review", comment="over to you", actor="agent:berna/w1")

    with pytest.raises(GuardFailed, match="nobody on berna closes work berna produced"):
        update(repo, card, status="done", no_code=True, comment="mine",
               evidence="checked", actor="dev:berna")

    update(repo, card, status="done", no_code=True, comment="checked it",
           evidence="ran it", actor="dev:ana")


def test_peer_review_is_opt_in_and_a_solo_board_is_untouched(repo: Path) -> None:
    """The default has to keep a solo developer working: with nobody else on the board,
    refusing every close would make the tool unusable for the most common way it is first
    tried. A team states it once as a project decision."""
    card = plan(repo, [{"title": "t", "spec": "s", "acceptance": CRITERIA}],
                actor=DEV)["created"][0]["id"]
    next_task(repo, task=card, actor="agent:berna/w1")
    update(repo, card, status="review", comment="over to you", actor="agent:berna/w1")

    update(repo, card, status="done", no_code=True, comment="read the diff myself",
           evidence="ran it", actor="dev:berna")


def test_two_verifiers_cannot_check_the_same_card(repo: Path) -> None:
    """Watched live, and the user spotted it before I did. Dev:dos spawned its verifier AND
    read the diff itself; the verifier closed first, so the orchestrator's work was thrown
    away. The lease that prevents that existed and nothing made anybody take it.

    Now the CLOSE claims. A closer holding nothing gets the lease silently — which keeps a
    person closing a review they just read from having to claim first, the contract every
    existing flow depends on — and a second checker meets a held card instead of duplicating.
    """
    card = a_card(repo, criteria=CRITERIA)
    update(repo, card, status="review", comment="over to you", actor=WORKER)
    next_task(repo, task=card, actor="agent:berna/v1")      # v1 says "I am checking this"

    with pytest.raises(GuardFailed, match="already checking"):
        update(repo, card, status="done", no_code=True, comment="me too",
               evidence="ran it", actor="agent:berna/v2")

    update(repo, card, status="done", no_code=True, comment="mine",
           evidence="ran it", actor="agent:berna/v1")


def test_closing_a_review_nobody_holds_needs_no_ceremony(repo: Path) -> None:
    """The contract that had to survive: a person who just read a review closes it, full stop.
    The lease is taken for them rather than demanded from them."""
    card = a_card(repo, criteria=CRITERIA)
    update(repo, card, status="review", comment="over to you", actor=WORKER)

    update(repo, card, status="done", no_code=True, comment="read it myself",
           evidence="checked", actor=DEV)


def test_a_verifier_that_went_quiet_can_be_taken_over(repo: Path) -> None:
    """A held card must not be held forever by somebody who died. The refusal names the way
    out, and the way out is the verb that already exists for it."""
    from taskops.usecases import recover

    card = a_card(repo, criteria=CRITERIA)
    update(repo, card, status="review", comment="over to you", actor=WORKER)
    next_task(repo, task=card, actor="agent:berna/v1")

    recover(repo, actor=DEV, force=True)

    update(repo, card, status="done", no_code=True, comment="took it over",
           evidence="ran it", actor="agent:berna/v2")


def test_a_rejection_and_a_close_racing_leave_exactly_one_outcome(repo: Path) -> None:
    """The live failure, reproduced: verifier v2 rejected a card `review → ready` with
    findings, and seventeen seconds later verifier v1 closed the SAME card `review → done` —
    its guard was still judging the snapshot it had read before the rejection landed, because
    `update` took the write lock only at the write. A card rejected for breaking an invariant
    ended up done, and both events sat in the log claiming to come `from: review`.

    Not a new guard: the same BEGIN-IMMEDIATE law `claim` has lived under since its own race,
    applied to the only other verb that writes. Whoever loses the lock rereads the present and
    the state machine refuses them.
    """
    import threading

    card = a_card(repo, criteria=CRITERIA)
    update(repo, card, status="review", comment="over to you", actor=WORKER)

    outcomes: dict[str, object] = {}
    gate = threading.Barrier(2)

    def racer(name: str, status: str, actor: str) -> None:
        gate.wait()
        try:
            update(repo, card, status=status, comment=f"{name} says",
                   no_code=True, evidence="ran it", actor=actor)
            outcomes[name] = "landed"
        except Exception as refused:  # noqa: BLE001 — the refusal IS the assertion
            outcomes[name] = type(refused).__name__

    threads = [threading.Thread(target=racer, args=("reject", "ready", "agent:berna/v2")),
               threading.Thread(target=racer, args=("close", "done", "agent:berna/v1"))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert list(outcomes.values()).count("landed") == 1, \
        f"exactly one racer may land, got {outcomes}"
    final = ask(repo, card)["task"]["status"]
    assert (final == "ready") == (outcomes["reject"] == "landed"), outcomes


def test_a_card_reserved_for_one_person_is_not_closed_by_another(repo: Path) -> None:
    """`reviewer: dev:berna` names a PERSON, not a category — and the guard read it as one.

    Found by a question rather than a run: "I work with a team but I want to review and close
    the cards myself." That is exactly what naming yourself on a card is for, and it did not
    work — the rule asked "is the closer a person" and stopped there, so a teammate closed a
    card its author had reserved. `human` still means whoever shows up; a named dev means them.
    """
    from taskops.usecases import plan as plan_cards

    card = plan_cards(repo, [{"title": "Mine to read", "spec": "x", "reviewer": "dev:berna",
                              "acceptance": CRITERIA}], actor=DEV)["created"][0]["id"]
    next_task(repo, task=card, actor=WORKER)
    update(repo, card, status="review", comment="over to you", actor=WORKER)

    with pytest.raises(GuardFailed) as refused:
        closes(repo, card, "dev:ana")
    assert "dev:berna" in str(refused.value), "the refusal has to name who is expected"

    closes(repo, card, "dev:berna")


def test_reviewer_human_still_means_whichever_person_arrives(repo: Path) -> None:
    """The other half, and the reason the fix is narrow: `human` is a category on purpose —
    a card that only needs eyes must not wait for one specific pair."""
    from taskops.usecases import plan as plan_cards

    card = plan_cards(repo, [{"title": "Any human", "spec": "x", "reviewer": "human",
                              "acceptance": CRITERIA}], actor=DEV)["created"][0]["id"]
    next_task(repo, task=card, actor=WORKER)
    update(repo, card, status="review", comment="over to you", actor=WORKER)

    closes(repo, card, "dev:ana")
