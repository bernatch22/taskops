"""The whole agentic state machine, walked end to end — every transition an agent fleet makes.

This is THE test of the system: not one guard in isolation but the full life of a card through
real use cases against a real repository, exactly the sequence a manager, a worker, a verifier
and a human perform. When something here breaks, an agent somewhere is stranded — every hole
this file pins was first found live, with a worker stuck on it.

The lifecycle under test:

    plan ──▶ assign ──▶ claim ──▶ review ──▶ done
              (hides)   (lease)                    │  ▲  │
                                                   │  │  └── by ANOTHER actor, with evidence
                                     findings ─────┘  │
                                     worker re-claims ┘   (review released the lease)
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from taskops._clock import now
from taskops._errors import GuardFailed
from taskops.storage import Store
from taskops.usecases import dispatch, init, next_task, plan, update

DEV = "dev:berna"
WORKER = "agent:berna/api"
VERIFIER = "agent:berna/tester"
INTRUDER = "agent:berna/intruder"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "b@example.com"),
                 ("config", "user.name", "Berna")):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    init(tmp_path)
    return tmp_path


def leases_of(repo: Path, task: str) -> list[str]:
    with Store(repo) as store:
        return [row["actor"] for row in store.db.execute(
            "SELECT actor FROM leases WHERE task=? AND expires > ?", (task, now()))]


def test_the_full_lifecycle_hand_to_hand(repo: Path) -> None:
    """One card, every hand it passes through, every fact asserted at each step."""
    # PLAN: the manager creates it, with a spec and criteria — dispatchable work.
    card = plan(repo, [{"title": "the feature", "spec": "DONE = the gap test passes",
                        "acceptance": ["WHEN x THE SYSTEM SHALL y"]}],
                actor=DEV)["created"][0]["id"]

    # ASSIGN: dispatch binds it to the worker BEFORE anything could claim it...
    dispatch(repo, tasks=(card,), actor=DEV, prefix="api")
    stranger = next_task(repo, task=card, actor=INTRUDER)
    assert stranger["claim"] is None, "...and from that moment no other agent can have it"

    # CLAIM: the assignee says who it is and takes its own card.
    assignee = "agent:berna/api1"
    held = next_task(repo, task=card, actor=assignee)
    assert held["claim"] is not None
    assert leases_of(repo, card) == [assignee]

    # WORK: a comment renews the lease and says what is happening; there is no second
    # "started" state to announce — claimed IS working.
    update(repo, card, comment="on it", actor=assignee)

    # REVIEW: the handoff. The work is finished, so the LEASE is released — a held card would
    # say "in hand" about nobody, which is exactly how a verifier got refused live.
    update(repo, card, status="review", comment="criterion 1: met via the gap test",
           actor=assignee)
    assert leases_of(repo, card) == [], "review is a handoff, not a hold"

    # SELF-CLOSE REFUSED: the one who asked for the review may not declare it passed.
    with pytest.raises(GuardFailed, match="another's to close"):
        update(repo, card, status="done", no_code=True, comment="done by me",
               evidence="trust me", actor=assignee)

    # CLOSE: a different actor, with evidence. No lease needed — closing is judging, and the
    # judge holds nothing.
    update(repo, card, status="done", no_code=True, comment="verified",
           evidence="criterion 1: the gap test passes, ran it", actor=VERIFIER)

    with Store(repo) as store:
        assert store.tasks.need(card)["status"] == "done"


def test_the_bounce_back_walks_the_whole_circle(repo: Path) -> None:
    """Findings send it back; the worker RE-CLAIMS (review released the lease), fixes, hands
    it over again, and the verifier closes. The full agentic loop, twice around."""
    card = plan(repo, [{"title": "the feature", "spec": "s",
                        "acceptance": ["WHEN x THE SYSTEM SHALL y"]}],
                actor=DEV)["created"][0]["id"]
    next_task(repo, task=card, actor=WORKER)
    update(repo, card, status="review", comment="round 1", actor=WORKER)

    # The verifier reads it without claiming anything and posts findings.
    update(repo, card, comment="FAILS: criterion 1 — nothing asserts y", actor=VERIFIER)

    # The worker returns. Claiming lands on `claimed`: the findings are in and the card is
    # its own again, with no review pending for the guard to refuse it over.
    back = next_task(repo, task=card, actor=WORKER)
    assert back["claim"] is not None, "the bounced-back card must be reachable by its worker"
    with Store(repo) as store:
        assert store.tasks.need(card)["status"] == "claimed", (
            "coming back to a bounced card IS leaving the handoff — it is the worker's again")

    update(repo, card, comment="picking findings up", actor=WORKER)
    update(repo, card, status="review", comment="round 2: y asserted", actor=WORKER)
    update(repo, card, status="done", no_code=True, comment="holds now",
           evidence="criterion 1: asserted", actor=VERIFIER)


def test_an_intruder_cannot_take_a_review_card_by_id(repo: Path) -> None:
    """Claimable-in-review is for the ASSIGNEE coming back, not a door for anyone to grab
    work in its most fragile state. Unassigned review cards stay open to any claimer — the
    worker may have died — but one that is somebody's is theirs."""
    card = plan(repo, [{"title": "t", "spec": "s"}], actor=DEV)["created"][0]["id"]
    dispatch(repo, tasks=(card,), actor=DEV, prefix="api")
    mine = "agent:berna/api1"
    next_task(repo, task=card, actor=mine)
    update(repo, card, status="review", comment="ready", actor=mine)

    stolen = next_task(repo, task=card, actor=INTRUDER)
    assert stolen["claim"] is None


def test_a_review_card_never_reaches_the_pool(repo: Path) -> None:
    """`next` with no task must not hand out a card in its handoff: the pool is for work
    nobody started, and a review card is work somebody finished."""
    card = plan(repo, [{"title": "t", "spec": "s"}], actor=DEV)["created"][0]["id"]
    next_task(repo, task=card, actor=WORKER)
    update(repo, card, status="review", comment="ready", actor=WORKER)

    pooled = next_task(repo, actor=INTRUDER)
    assert pooled["claim"] is None, "the only card is in review — the pool must be empty"


def test_a_released_review_lease_cannot_be_swept_back_to_ready(repo: Path) -> None:
    """The reason releasing on review is SAFE: with no lease left to expire, `sweep_dead`
    has nothing to lapse, so a card cannot fall out of review because time passed."""
    from taskops.engine import sweep_dead

    card = plan(repo, [{"title": "t", "spec": "s"}], actor=DEV)["created"][0]["id"]
    next_task(repo, task=card, actor=WORKER)
    update(repo, card, status="review", comment="ready", actor=WORKER)

    with Store(repo) as store:
        sweep_dead(store, at=now() + 10_000_000)
        assert store.tasks.need(card)["status"] == "review", "review outlives every clock"



def test_a_refused_move_never_costs_the_commit_binding(repo: Path) -> None:
    """The ordering, learned in one run. This hook fires as whoever git says made the commit —
    often the DEVELOPER, while the lease belongs to an agent — so the move hits the lease guard.
    Attempted first, that refusal took the binding down with it: the card lost the commit it
    exists to be bound to, over a status nobody asked for."""
    from taskops.usecases import ask, ingest_commit

    card = plan(repo, [{"title": "t", "spec": "s"}], actor=DEV)["created"][0]["id"]
    claim = next_task(repo, task=card, actor=WORKER)["claim"]
    assert claim is not None

    subprocess.run(["git", "switch", "-qc", claim["branch"]], cwd=repo, check=True)
    (repo / "a.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", f"work\n\nTask: {card}"], cwd=repo, check=True)

    # A DEV ingests it — no lease, so the status move will be refused.
    ingest_commit(repo, actor=DEV)

    view = ask(repo, card)
    assert view["commits"], "the binding survives a refused status move"
    with Store(repo) as store:
        assert store.tasks.need(card)["status"] == "claimed", "and the move really was refused"


def test_the_verifier_needs_exactly_two_verbs(repo: Path) -> None:
    """The whole review protocol, as the verifier prompt states it: done-with-evidence to
    close, ready-with-findings to send back. Neither takes a lease. A live run burned a whole
    session discovering that the second verb did not exist and the first dropped its evidence
    on the MCP floor."""
    card = plan(repo, [{"title": "t", "spec": "s",
                        "acceptance": ["WHEN x THE SYSTEM SHALL y"]}],
                actor=DEV)["created"][0]["id"]
    dispatch(repo, tasks=(card,), actor=DEV, prefix="w")
    worker = "agent:berna/w1"
    next_task(repo, task=card, actor=worker)
    update(repo, card, status="review", comment="round 1", actor=worker)

    # SEND BACK: one call, no lease, findings in the comment. The assignee survives.
    update(repo, card, status="ready", comment="FAILS: nothing asserts y", actor=VERIFIER)
    with Store(repo) as store:
        after = store.tasks.need(card)
        assert after["status"] == "ready"
        assert after["assignee"] == worker, "sent back to ITS worker, not to the pool"

    stranger = next_task(repo, task=card, actor=INTRUDER)
    assert stranger["claim"] is None, "assigned means assigned, even after a send-back"

    # The worker picks it up again and hands it over; the verifier closes. Two calls each.
    next_task(repo, task=card, actor=worker)
    update(repo, card, status="review", comment="round 2: asserted", actor=worker)
    update(repo, card, status="done", no_code=True, comment="verified",
           evidence="WHEN x THE SYSTEM SHALL y: asserted, ran it", actor=VERIFIER)


def test_a_card_with_nothing_to_check_closes_without_a_review(repo: Path) -> None:
    """Review is OPTIONAL, and the engine always said so — what made it feel mandatory was the
    instructions. A card that named no reviewer and promised no criteria has nothing for a
    verifier to check against, and spawning one to read a diff with no criteria costs a model
    and answers nothing."""
    card = plan(repo, [{"title": "tidy the imports", "spec": "s"}], actor=DEV)["created"][0]["id"]
    next_task(repo, task=card, actor=WORKER)

    update(repo, card, status="done", no_code=True, comment="no code, just the imports",
           evidence="ran the linter", actor=WORKER)

    with Store(repo) as store:
        assert store.tasks.need(card)["status"] == "done"


def test_in_progress_is_gone_from_the_vocabulary(repo: Path) -> None:
    """It meant "claimed and actually working", which is what claimed already meant to everyone
    using the board: ONE transition to it in the whole history of this project, written by hand
    in a test. A state nobody enters is a column that splits attention and answers nothing."""
    from taskops._errors import IllegalTransition
    from taskops._types import STATUSES

    assert "in_progress" not in STATUSES
    card = plan(repo, [{"title": "t", "spec": "s"}], actor=DEV)["created"][0]["id"]
    next_task(repo, task=card, actor=WORKER)
    with pytest.raises(IllegalTransition, match="in_progress"):
        update(repo, card, status="in_progress", comment="on it", actor=WORKER)


def test_a_log_that_still_carries_in_progress_replays_as_claimed(repo: Path) -> None:
    """Replay is the one reader that may never refuse history: a teammate on an older taskops
    is still writing that status, and it lands where it always belonged."""
    from taskops.engine import replay
    from taskops.engine.log import build

    card = plan(repo, [{"title": "t", "spec": "s"}], actor=DEV)["created"][0]["id"]
    theirs = build(task=card, actor="agent:ana/old", kind="status",
                   body={"from": "claimed", "to": "in_progress"}, ts=now() + 60)

    with Store(repo) as store:
        assert replay.apply(store, [theirs]) >= 0
        assert store.tasks.need(card)["status"] == "claimed"


def test_criteria_make_review_MANDATORY_for_an_agent(repo: Path) -> None:
    """The critical one, found live: a card with three EARS criteria went straight from claimed
    to done, signed by the agent that wrote it, minutes after review was made optional. A card
    carrying criteria is EXACTLY the card somebody else should check — that is what criteria
    are for — and a worker signing off on its own is the self-certification the loop exists to
    prevent."""
    card = plan(repo, [{"title": "t", "spec": "s",
                        "acceptance": ["WHEN x THE SYSTEM SHALL y"]}],
                actor=DEV)["created"][0]["id"]
    next_task(repo, task=card, actor=WORKER)

    with pytest.raises(GuardFailed, match="acceptance criteria"):
        update(repo, card, status="done", no_code=True, comment="mine",
               evidence="I checked it", actor=WORKER)

    update(repo, card, status="review", comment="criterion 1 met", actor=WORKER)
    update(repo, card, status="done", no_code=True, comment="verified",
           evidence="WHEN x THE SYSTEM SHALL y: ran it", actor=VERIFIER)


def test_a_dev_closes_a_card_with_criteria_without_ceremony(repo: Path) -> None:
    """A human reading the diff IS the review. Making a person hand their own card to an agent
    before they could close it would get the guard removed within the hour."""
    card = plan(repo, [{"title": "t", "spec": "s",
                        "acceptance": ["WHEN x THE SYSTEM SHALL y"]}],
                actor=DEV)["created"][0]["id"]
    next_task(repo, task=card, actor=DEV)
    update(repo, card, status="done", no_code=True, comment="read it myself",
           evidence="WHEN x…: checked", actor=DEV)


def test_a_card_with_nothing_promised_still_closes_in_one_step(repo: Path) -> None:
    """The regression guard for the case review was made optional FOR: a text fix promises
    nothing checkable, so there is nothing for a verifier to check against."""
    card = plan(repo, [{"title": "fix the copy", "spec": "s"}], actor=DEV)["created"][0]["id"]
    next_task(repo, task=card, actor=WORKER)
    update(repo, card, status="done", no_code=True, comment="typo", evidence="read it",
           actor=WORKER)
