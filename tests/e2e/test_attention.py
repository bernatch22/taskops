"""The sweep that replaced the channel, against a real repository.

Board events used to be pushed into an open session so it could react to them. Every one of
those reactions was idempotent and derivable from state, so the state can be asked instead —
and these tests are the proof of that claim, one per event the channel used to deliver.

They are e2e rather than unit for the same reason `test_review_loop` is: nothing STORES "this
card is waiting on somebody", so the answer has to come back out of tasks, leases, assignments
and the dependency graph. A test that handed the engine a literal would prove nothing about the
derivation, which is the whole mechanism.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from taskops.usecases import attention, dispatch, init, next_task, plan, update

WORKER = "agent:berna/one"
DEV = "dev:berna"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "b@example.com"),
                 ("config", "user.name", "Berna")):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    init(tmp_path)
    return tmp_path


def a_card(repo: Path, **fields: object) -> str:
    entry = {"title": "t", "spec": "s", **fields}
    return plan(repo, [entry], actor=DEV)["created"][0]["id"]


def moves(repo: Path) -> dict[str, str]:
    """Card id -> the move the sweep says it needs. The whole surface these tests assert on."""
    return {item["task"]["id"]: item["move"] for item in attention(repo)["waiting"]}


def test_a_review_nobody_verified_is_the_first_thing_it_reports(repo: Path) -> None:
    """The channel's flagship event. A card handed over sits in `review` with its lease
    released, so nothing on the board is going to move it — and unlike the notification, this
    is still true tomorrow morning, which is the deployment the channel never served."""
    card = a_card(repo)
    next_task(repo, task=card, actor=WORKER)
    update(repo, card, status="review", comment="done my half", actor=WORKER)

    assert moves(repo)[card] == "verify"
    assert attention(repo)["waiting"][0]["task"]["id"] == card


def test_a_card_being_worked_on_right_now_is_not_waiting_on_anybody(repo: Path) -> None:
    """The refusal that makes the sweep safe to act on. A live lease means an agent is on it,
    so listing it would have an orchestrator dispatch a second worker into the same card —
    the collision the board exists to prevent."""
    card = a_card(repo)
    next_task(repo, task=card, actor=WORKER)

    assert card not in moves(repo)


def test_a_card_assigned_to_a_worker_that_never_started_is_reported_to_resume(
        repo: Path) -> None:
    """Assignment HIDES a card from every other agent — that hiding is what makes it useful —
    so a dispatch nobody spawned is invisible and unclaimable forever. Eight of them sat like
    that once, and the only thing that found them was somebody counting by hand."""
    card = a_card(repo)
    dispatch(repo, tasks=(card,), actor=DEV)

    assert moves(repo)[card] == "resume"


def test_ready_work_is_reported_to_dispatch_and_specless_work_is_not(repo: Path) -> None:
    """Two groups, and the split is the one `dispatch` already enforces: a worker handed a
    title with no spec can only guess or give up, and both happened to one card in one day."""
    solid, empty = a_card(repo), a_card(repo, spec="")

    assert moves(repo) == {solid: "dispatch", empty: "specless"}


def test_a_parked_card_is_reported_because_nothing_else_will_ever_move_it(
        repo: Path) -> None:
    """`unblock` only scans `backlog` and `ready`, so a card an agent parked with `blocked_on`
    stays there until a person moves it — and on a board it reads exactly like a card somebody
    is working on. That is "never leave a story dead", found by the engine refusing the version
    of this test that assumed a cancelled DEPENDENCY was the dead end (it is not: `unblock`
    counts cancelled as closed and frees the card)."""
    created = plan(repo, [{"title": "first", "spec": "s"},
                          {"title": "second", "spec": "s", "after": 0}], actor=DEV)["created"]
    blocker, waiting = created[0]["id"], created[1]["id"]
    assert waiting not in moves(repo)

    update(repo, blocker, status="cancelled", comment="not doing this", actor=DEV)
    assert moves(repo)[waiting] == "dispatch", "a cancelled dependency frees its card"

    next_task(repo, task=waiting, actor=WORKER)
    update(repo, waiting, status="blocked", comment="need a decision", actor=WORKER)

    assert moves(repo)[waiting] == "stalled"


def test_finishing_is_reported_before_starting(repo: Path) -> None:
    """The order is a claim, not a sort: closing a review may unblock three cards, while a
    dispatch adds a fourth thing in flight. An orchestrator reads this top-down and should
    reach the work that ENDS things first."""
    fresh = a_card(repo)
    handed = a_card(repo)
    next_task(repo, task=handed, actor=WORKER)
    update(repo, handed, status="review", comment="over to you", actor=WORKER)

    assert [item["move"] for item in attention(repo)["waiting"]] == ["verify", "dispatch"]
    assert attention(repo)["waiting"][1]["task"]["id"] == fresh


def test_a_board_where_everything_is_in_hand_says_so_rather_than_printing_nothing(
        repo: Path) -> None:
    """`quiet` is named rather than left to `not waiting` because an empty board and a board
    whose every card is being worked on are the same list and different situations."""
    card = a_card(repo)
    next_task(repo, task=card, actor=WORKER)

    assert attention(repo)["quiet"] is True


def test_the_sweep_writes_nothing(repo: Path) -> None:
    """The line between this and `recover`. A sweep that fixed what it found would be a second
    dispatcher running on a timer, and there is exactly one: the orchestrator decides."""
    card = a_card(repo)
    dispatch(repo, tasks=(card,), actor=DEV)
    log = (repo / ".taskops" / "events.jsonl").read_bytes()

    attention(repo)
    attention(repo)

    assert (repo / ".taskops" / "events.jsonl").read_bytes() == log


def test_a_parked_card_surfaces_even_though_its_worker_still_holds_the_lease(
        repo: Path) -> None:
    """Found by the test above. Parking keeps the lease — only `ready`, `review`, `done` and
    `cancelled` release one — so a card an agent had just declared itself blocked on went on
    looking busy for the fifteen minutes until the TTL ran out. Its own declaration is the
    better evidence, so `blocked` is judged BEFORE the lease."""
    card = a_card(repo)
    next_task(repo, task=card, actor=WORKER)
    update(repo, card, status="blocked", comment="need a decision", actor=WORKER)

    assert moves(repo)[card] == "stalled"


def test_a_review_surfaces_even_when_a_stale_lease_says_somebody_holds_it(repo: Path) -> None:
    """Found by running two clones against a real server. Handing a card over releases its
    lease, so a `review` card holding one is a card whose lease is WRONG — and with a remote
    that is routine, because transitions execute in the server's database and the client
    mirrors the task, not the lease release. The machine that did the work keeps a live lease
    on a card it already handed over, and the sweep went quiet on the one board that most
    needed to say somebody has to verify this."""
    from taskops._clock import now
    from taskops.contracts import Lease
    from taskops.storage import Store

    card = a_card(repo)
    next_task(repo, task=card, actor=WORKER)
    update(repo, card, status="review", comment="over to you", actor=WORKER)
    with Store(repo) as store:
        store.leases.acquire(Lease(task=card, actor=WORKER, session="s", branch="b",
                                   acquired=now(), expires=now() + 900))   # the stale mirror
        assert [lease["task"] for lease in store.leases.live(now())] == [card]

    assert moves(repo)[card] == "verify"
