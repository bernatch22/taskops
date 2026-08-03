"""One review, ONE reviewer — the end of the broadcast, walked end to end.

The failure this file exists for was watched live and is easy to state: two developers were
free, a card entered `review` with `reviewer: peer`, and BOTH sweeps offered it. Both started.
Two agents read the same diff, and the second one's work was thrown away the instant the first
closed the card. Nothing was broken — every rule was obeyed — the card was simply announced to
everybody eligible, and "eligible" is not "assigned".

So routing is a WRITE, not a filter: entering review picks one connected developer and puts the
card in their name. Everything here checks the three consequences of that — the chosen dev sees
it, nobody else does, and the choice spreads the load rather than always landing on the same
person.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from taskops._errors import GuardFailed
from taskops.engine.routereview import ROUTE_TTL
from taskops.usecases import attention, init, next_task, plan, update
from taskops.usecases.session import brief

CRITERIA = ["WHEN a review is routed THE SYSTEM SHALL offer it to exactly one developer"]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "b@example.com"),
                 ("config", "user.name", "Berna")):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    init(tmp_path)
    return tmp_path


def here(repo: Path, *devs: str) -> None:
    """Open a SESSION for each of these developers — which is what "connected" means.

    It used to be any read, and that is the hole a live board fell into: the manager who had
    created the cards from a terminal four minutes earlier counted as present, so a review was
    routed to somebody who was never coming back. A session announces itself once (the
    SessionStart read carries the id) and every later call keeps it alive.
    """
    for dev in devs:
        brief(repo, actor=dev, session=f"s-{dev}")


def handed_over(repo: Path, title: str = "t", *, by: str = "agent:uno/w1") -> str:
    card = plan(repo, [{"title": title, "spec": "s", "acceptance": CRITERIA, "reviewer": "peer"}],
                actor="dev:uno")["created"][0]["id"]
    next_task(repo, task=card, actor=by)
    update(repo, card, status="review", comment="over to you", actor=by)
    return str(card)


def handed_over_to(repo: Path) -> tuple[str, str]:
    """A card in review, and the dev the SERVER chose for it — never a guess.

    Which dev wins is a real decision (load, then freshness, then name), so a test that
    hard-codes the answer is testing its own arithmetic. Asking the call is also the honest
    shape: this is exactly what the author is told.
    """
    card = plan(repo, [{"title": "t", "spec": "s", "acceptance": CRITERIA, "reviewer": "peer"}],
                actor="dev:uno")["created"][0]["id"]
    next_task(repo, task=card, actor="agent:uno/w1")
    result = update(repo, card, status="review", comment="over to you", actor="agent:uno/w1")
    return card, str(result["routed_to"])


def offered_to(repo: Path, dev: str) -> set[str]:
    return {item["task"]["id"] for item in attention(repo, actor=dev)["waiting"]
            if item["move"] == "verify"}


def test_a_handover_reaches_exactly_one_of_the_free_developers(repo: Path) -> None:
    """The whole design in one assertion: three devs connected, one card, one offer."""
    here(repo, "dev:uno", "dev:dos", "dev:tres")
    card = handed_over(repo)

    offered = [dev for dev in ("dev:uno", "dev:dos", "dev:tres") if card in offered_to(repo, dev)]
    assert offered in (["dev:dos"], ["dev:tres"]), (
        f"a routed review must reach one non-author dev, not {offered}")


def test_the_author_is_never_the_one_it_is_routed_to(repo: Path) -> None:
    here(repo, "dev:uno", "dev:dos")
    card = handed_over(repo)
    assert card not in offered_to(repo, "dev:uno")


def test_with_nobody_else_connected_the_card_stays_open_to_whoever_arrives(repo: Path) -> None:
    """The failure mode routing must NOT have. If picking one reviewer meant picking one when
    there is nobody to pick, a solo session would hand a card over and bury it: routed to an
    empty string, hidden from everybody, waiting on a person who never comes. Unrouted is the
    honest state — the sweep goes back to offering it to every eligible dev."""
    here(repo, "dev:uno")
    card = handed_over(repo)
    assert card in offered_to(repo, "dev:dos"), "unrouted means open, not buried"


def test_the_load_spreads_instead_of_landing_on_the_same_developer(repo: Path) -> None:
    """Two cards, two free reviewers, one each — because the pick is ordered by how many
    reviews a dev is already carrying before anything else. Sorting by presence alone would
    give both to whoever spoke last, which is a broadcast with extra steps."""
    here(repo, "dev:uno", "dev:dos", "dev:tres")
    first, second = handed_over(repo, "one"), handed_over(repo, "two")

    got = {dev: offered_to(repo, dev) for dev in ("dev:dos", "dev:tres")}
    assert got["dev:dos"] | got["dev:tres"] == {first, second}
    assert len(got["dev:dos"]) == len(got["dev:tres"]) == 1, f"one each, got {got}"


def test_the_developer_it_was_routed_to_claims_it_through_an_agent(repo: Path) -> None:
    """Routing names a DEV; reviewing is done by that dev's sub-agent. If the claim compared
    ids exactly, the card would refuse the very verifier it was routed to."""
    here(repo, "dev:uno", "dev:dos")
    card = handed_over(repo)

    assert next_task(repo, task=card, actor="agent:dos/verifier")["claim"] is not None


def test_a_stranger_cannot_take_a_review_routed_to_somebody_else(repo: Path) -> None:
    here(repo, "dev:uno", "dev:dos")
    card = handed_over(repo)

    assert next_task(repo, task=card, actor="agent:tres/verifier")["claim"] is None


def test_a_routing_nobody_acted_on_expires_and_the_card_opens_again(repo: Path) -> None:
    """Routing is a nudge with a deadline, not a lock. The dev it went to may have closed their
    laptop; a card that stayed theirs forever would be exactly the dead story this project
    refuses. After the TTL the sweep offers it to everybody eligible again."""
    here(repo, "dev:uno", "dev:dos")
    card = handed_over(repo)
    assert card not in offered_to(repo, "dev:tres")

    from taskops.storage import Store
    with Store(repo) as store:
        store.db.execute("UPDATE tasks SET updated = updated - ? WHERE id = ?",
                         (ROUTE_TTL + 60, card))
        store.db.commit()

    assert card in offered_to(repo, "dev:tres"), "an expired routing must reopen the card"
    assert next_task(repo, task=card, actor="agent:tres/verifier")["claim"] is not None


def test_the_reviewer_can_be_woken_without_a_channel_at_all(repo: Path) -> None:
    """The deployment with NO channel, which is the one that has to work anyway.

    A routed review reaches its reviewer as a MESSAGE, and the sweep is what a poll reads. If
    `quiet` ignored mail, `attention --wait` would sleep straight through the one event
    somebody chose this session for — the exact class of thing the channel delivers when it is
    running. Both paths carry the same fact; only the transport differs.
    """
    here(repo, "dev:uno", "dev:dos")
    card = handed_over(repo)

    woken = attention(repo, actor="dev:dos")
    assert woken["mail"] >= 1, "the routed review has to reach its reviewer as a message"
    assert not woken["quiet"], "a poll blocks on `quiet`; mail must break it"
    assert card in {item["task"]["id"] for item in woken["waiting"]}


def test_the_author_is_not_woken_by_its_own_handover(repo: Path) -> None:
    """The other half of the same rule, and the one that made the old channel unreadable: a
    session hearing about what its own agents just did is hearing its own return value."""
    here(repo, "dev:uno", "dev:dos")
    handed_over(repo)

    assert attention(repo, actor="dev:uno")["quiet"], "no echo, and nothing to decide"


# ------------------------------------------------------ what the first live run got wrong

def test_a_dev_who_only_ran_a_command_is_never_routed_to(repo: Path) -> None:
    """The ghost reviewer, watched on a live board.

    A manager created the cards from a terminal and left. Four minutes later a card entered
    review and was routed to them — present by every measure the store had, and never coming
    back. `dev:mgr` here does exactly that: it plans, and it never opens a session.

    A session BEATS a passing call; it is not a requirement. See the test below for why.
    """
    here(repo, "dev:uno", "dev:dos")
    plan(repo, [{"title": "x", "spec": "s"}], actor="dev:mgr")      # a passing call, no session
    card = handed_over(repo)

    assert card in offered_to(repo, "dev:dos"), "the routing must land on the session that is up"
    assert card not in offered_to(repo, "dev:mgr")


def test_with_no_session_anywhere_it_still_routes_to_somebody(repo: Path) -> None:
    """The regression that made the fix worse than the bug, caught in a live run.

    Requiring a session made the session signal load-bearing, and it was not arriving: it is
    written by the SessionStart read, which is local, while presence lives where the routing
    runs. Every row had an empty session, no developer was ever a candidate, three handovers
    in a row were routed to NOBODY, and one card sat orphaned in review with nothing said
    about it anywhere.

    A ghost reviewer waits and then expires. No reviewer at all is a card nothing ever
    mentions — strictly worse, so the session narrows the field only when it exists.
    """
    plan(repo, [{"title": "x", "spec": "s"}], actor="dev:dos")     # present, no session
    card, owner = handed_over_to(repo)

    assert owner == "dev:dos", "somebody has to be told, even with no session signal at all"
    assert card in offered_to(repo, "dev:dos")


def test_a_stranger_cannot_CLOSE_a_review_routed_to_somebody_else(repo: Path) -> None:
    """The door the first version left unlocked.

    Routing guarded the claim and not the close, so on a live board a card routed to one
    developer went straight from `review` to `done` signed by a second — no claim at all,
    because a `dev:` actor passes every other closing rule by design.
    """
    here(repo, "dev:uno", "dev:dos", "dev:tres")
    card, owner = handed_over_to(repo)
    stranger = "dev:tres" if owner != "dev:tres" else "dev:dos"

    with pytest.raises(GuardFailed) as refused:
        update(repo, card, status="done", comment="yo la cierro", actor=stranger,
               no_code=True, evidence="the criterion: checked")
    assert "routed" in str(refused.value)


def test_the_dev_it_was_routed_to_still_closes_it(repo: Path) -> None:
    """The other half, and the one that would make the guard a bug if it failed."""
    here(repo, "dev:uno", "dev:dos")
    card, owner = handed_over_to(repo)

    update(repo, card, status="done", comment="revisada", actor=owner,
           no_code=True, evidence="the criterion: checked by hand")
    assert next(t for t in _tasks(repo) if t["id"] == card)["status"] == "done"


def test_the_author_is_TOLD_the_review_left_and_is_not_theirs(repo: Path) -> None:
    """Silence was the design, and the author filled it.

    A session whose two workers handed cards over spawned a verifier for each of them a minute
    later — nothing had told it not to, both were refused at the close, and two agents were
    spent. The channel must stay silent towards the author (that is the echo), so the author's
    OWN call is what has to say it.
    """
    from taskops.render.results import render_update

    here(repo, "dev:uno", "dev:dos")
    card = plan(repo, [{"title": "t", "spec": "s", "acceptance": CRITERIA, "reviewer": "peer"}],
                actor="dev:uno")["created"][0]["id"]
    next_task(repo, task=card, actor="agent:uno/w1")
    result = update(repo, card, status="review", comment="over to you", actor="agent:uno/w1")

    assert result["routed_to"] == "dev:dos"
    said = render_update(result)
    assert "do not spawn a verifier" in said.lower(), "a prohibition, not bookkeeping"


def test_the_stop_hook_never_names_a_card_routed_to_another_dev(repo: Path) -> None:
    """What the hook says IS an order: a session is blocked until it acts on that list."""
    from taskops.usecases.pending import unverified

    here(repo, "dev:uno", "dev:dos")
    card = handed_over(repo)

    assert card not in {row["task"]["id"] for row in unverified(repo, actor="dev:uno")}
    assert card in {row["task"]["id"] for row in unverified(repo, actor="dev:dos")}


def _tasks(repo: Path) -> list[dict[str, object]]:
    from taskops.storage import Store
    with Store(repo) as store:
        return [dict(task) for task in store.tasks.all()]


def test_a_handover_that_reached_nobody_says_so(repo: Path) -> None:
    """The orphan, made visible.

    A handover routed to nobody looked exactly like one that worked — same status, same
    silence — so a card sat in review that no message anywhere mentioned. The author is the
    one person positioned to notice, and the return value is the message they will read.
    """
    from taskops.render.results import render_update

    card = plan(repo, [{"title": "solo", "spec": "s", "acceptance": CRITERIA, "reviewer": "peer"}],
                actor="dev:uno")["created"][0]["id"]
    next_task(repo, task=card, actor="agent:uno/w1")
    result = update(repo, card, status="review", comment="a solas", actor="agent:uno/w1")

    assert result["routed_to"] == ""
    assert "routed to NOBODY" in render_update(result)


def test_the_routed_reviewer_claiming_LEAVES_the_card_in_review(repo: Path) -> None:
    """Routing writes the reviewer into `assignee`, and that broke a heuristic beside it.

    A claim on a review card asks one question: is this the worker coming BACK for findings
    (then the card is theirs again, `claimed`) or somebody saying "I am checking this" (then it
    must STAY in review, because every closing rule is written against a card in one)? The
    answer used to be `assignee == who` — true for a dispatched worker, and now also true for
    the dev the review was routed to. So the reviewer's own claim pulled the card out of
    review, and it closed from `claimed`, skipping the handoff guard and the routing guard.
    Four cards in one live run.
    """
    here(repo, "dev:uno", "dev:dos")
    card, owner = handed_over_to(repo)

    claimed = next_task(repo, task=card, actor=owner)["claim"]
    assert claimed is not None
    assert claimed["view"]["task"]["status"] == "review", (
        "the reviewer is checking it, not taking it back")


def test_the_worker_coming_back_for_findings_still_takes_the_card(repo: Path) -> None:
    """The other side, and the flow that would break if the fix went too far: a verifier
    rejects with findings, the worker re-claims, and the card is `claimed` again — its own,
    with no review pending. Refusing there strands the returning worker."""
    here(repo, "dev:uno", "dev:dos")
    card, owner = handed_over_to(repo)
    update(repo, card, status="ready", comment="findings: falta un caso", actor=owner)

    claimed = next_task(repo, task=card, actor="agent:uno/w1")["claim"]
    assert claimed is not None
    assert claimed["view"]["task"]["status"] == "claimed"
