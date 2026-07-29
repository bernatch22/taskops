"""The whole agentic state machine, walked end to end — every transition an agent fleet makes.

This is THE test of the system: not one guard in isolation but the full life of a card through
real use cases against a real repository, exactly the sequence a manager, a worker, a verifier
and a human perform. When something here breaks, an agent somewhere is stranded — every hole
this file pins was first found live, with a worker stuck on it.

The lifecycle under test:

    plan ──▶ assign ──▶ claim ──▶ in_progress ──▶ review ──▶ done
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

    # WORK: claimed -> in_progress needs the lease it has.
    update(repo, card, status="in_progress", comment="on it", actor=assignee)

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

    # The worker returns. Claiming a review card grants the lease and KEEPS the status —
    # stamping `claimed` over `review` would erase the fact the guard reads.
    back = next_task(repo, task=card, actor=WORKER)
    assert back["claim"] is not None, "the bounced-back card must be reachable by its worker"
    with Store(repo) as store:
        assert store.tasks.need(card)["status"] == "review", "claiming a review keeps review"

    update(repo, card, status="in_progress", comment="picking findings up", actor=WORKER)
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


def test_a_commit_moves_a_claimed_card_into_progress(repo: Path) -> None:
    """`in_progress` used to be a call an agent had to remember, and the numbers were blunt:
    ONE transition to it in the whole history of this project, written by hand in a test. The
    commit IS the work landing, so the card says so without anybody announcing it."""
    from taskops.usecases import ingest_commit

    card = plan(repo, [{"title": "t", "spec": "s"}], actor=DEV)["created"][0]["id"]
    claim = next_task(repo, task=card, actor=WORKER)["claim"]
    assert claim is not None

    subprocess.run(["git", "switch", "-qc", claim["branch"]], cwd=repo, check=True)
    (repo / "a.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", f"work\n\nTask: {card}"], cwd=repo, check=True)

    ingest_commit(repo, actor=WORKER)
    with Store(repo) as store:
        assert store.tasks.need(card)["status"] == "in_progress"


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
