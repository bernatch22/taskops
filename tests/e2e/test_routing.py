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

from taskops.engine.routereview import ROUTE_TTL
from taskops.usecases import attention, context_state, init, next_task, plan, update

CRITERIA = ["WHEN a review is routed THE SYSTEM SHALL offer it to exactly one developer"]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "b@example.com"),
                 ("config", "user.name", "Berna")):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    init(tmp_path)
    context_state(tmp_path, "decision", "reviewer: peer — we review each other", actor="dev:uno")
    return tmp_path


def here(repo: Path, *devs: str) -> None:
    """Make these developers present. A read is a heartbeat, which is the whole point: nothing
    has to announce itself, and a dev who stopped calling stops being routed to."""
    for dev in devs:
        attention(repo, actor=dev)


def handed_over(repo: Path, title: str = "t", *, by: str = "agent:uno/w1") -> str:
    card = plan(repo, [{"title": title, "spec": "s", "acceptance": CRITERIA}],
                actor="dev:uno")["created"][0]["id"]
    next_task(repo, task=card, actor=by)
    update(repo, card, status="review", comment="over to you", actor=by)
    return str(card)


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
