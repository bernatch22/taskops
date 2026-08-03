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


def test_a_review_a_verifier_is_holding_is_not_offered_to_anybody_else(repo: Path) -> None:
    """This REPLACES a test that pinned the opposite — that a review card must surface even
    with a live lease on it — and the replacement is the point rather than an accommodation.

    That test existed for a bug: a remote handover left a stale lease behind, because the
    mirror's copy of `LEASE_ENDS` had missed `review`. The stale lease is gone at the root now
    (one list, imported by both), so a LIVE lease on a review card has exactly one remaining
    meaning: a verifier claimed it and is checking. Showing it anyway is what had one real card
    verified three times in parallel, each run building its own venv.
    """
    card = a_card(repo)
    next_task(repo, task=card, actor=WORKER)
    update(repo, card, status="review", comment="over to you", actor=WORKER)
    assert moves(repo)[card] == "verify", "with nobody on it, it is everybody's to pick up"

    taken = next_task(repo, task=card, actor="agent:berna/verifier")

    assert taken["claim"] is not None
    assert card not in moves(repo), "somebody is checking it; it is that verifier's turn"


def test_a_verifier_claiming_a_review_leaves_it_in_review(repo: Path) -> None:
    """The close guard is written against a card that IS in review, so a verification claim
    may not walk it to `claimed` on the way in — that would make the verdict unlandable."""
    card = a_card(repo)
    next_task(repo, task=card, actor=WORKER)
    update(repo, card, status="review", comment="over to you", actor=WORKER)

    taken = next_task(repo, task=card, actor="agent:berna/verifier")

    assert taken["claim"]["view"]["task"]["status"] == "review"


def test_the_worker_coming_back_to_a_bounced_card_still_gets_it_claimed(repo: Path) -> None:
    """The other half, and the reason `lands_on` reads the log: the SAME agent returning to
    its own bounced card is leaving the handoff, not verifying it. Refusing that stranded the
    one worker the findings were addressed to."""
    card = a_card(repo)
    next_task(repo, task=card, actor=WORKER)
    update(repo, card, status="review", comment="done my half", actor=WORKER)

    back = next_task(repo, task=card, actor=WORKER)

    assert back["claim"]["view"]["task"]["status"] == "claimed"


def test_the_urgent_card_is_first_in_its_group(repo: Path) -> None:
    """The sort was descending, so `0 urgent … 3 whenever` came out backwards and the sweep
    recommended the least urgent work first. It went unseen because every card on a normal
    board carries the default — the bug only shows the day somebody marks something urgent,
    which on a live board was a priority-0 card sorting below eight priority-2 ones."""
    whenever = a_card(repo, priority=3)
    urgent = a_card(repo, priority=0)
    normal = a_card(repo)

    order = [item["task"]["id"] for item in attention(repo)["waiting"]]

    assert order == [urgent, normal, whenever]


def test_the_verifier_brief_tells_it_to_claim() -> None:
    """The brief said "do not claim the card", written when claiming a review walked it to
    `claimed` and broke the close guard. That changed — a claim now LEAVES a review card in
    review precisely so a verifier can take one — and the document was left contradicting the
    mechanism built for it, and without the tool to obey either version. Zero of eight reviews
    on a live board had a verifier holding them.

    A brief that forbids the mechanism is the same failure as a brief that names an agent type
    nobody installed: an instruction and a mechanism disagreeing, in writing."""
    import pathlib

    brief = (pathlib.Path(__file__).resolve().parents[2] / "src" / "taskops" / "assets" /
             "agents" / "taskops-verifier.md").read_text(encoding="utf-8")

    assert "taskops_next task=<id>" in brief, "it has to be told to take the lease"
    assert "mcp__taskops__taskops_next" in brief, "and given the tool to do it"
    assert "do not claim the card" not in brief.lower()


def test_a_review_this_actor_could_never_close_is_not_offered_to_them(repo: Path) -> None:
    """Watched in the second live run. The sweep told a developer to verify eleven cards their
    own agents had written, on a board whose `reviewer: peer` decision forbids exactly that —
    and the session spent six refused calls before working out that the rule is per TEAM, not
    per session, and said so in its own summary.

    Advice the engine will refuse is worse than no advice: it costs calls and it teaches the
    reader to stop trusting the list.
    """

    card = plan(repo, [{"title": "t", "spec": "s", "acceptance": ["WHEN x SHALL y"], "reviewer": "peer"}],
                actor=DEV)["created"][0]["id"]
    next_task(repo, task=card, actor="agent:berna/w1")
    update(repo, card, status="review", comment="over to you", actor="agent:berna/w1")

    assert card not in {i["task"]["id"] for i in attention(repo, actor="dev:berna")["waiting"]}
    assert card in {i["task"]["id"] for i in attention(repo, actor="dev:ana")["waiting"]}


def test_a_refusal_the_caller_could_fix_is_still_listed(repo: Path) -> None:
    """The line is drawn at "cannot change by trying". A missing commit, missing evidence, an
    open child — every one of those is fixable BY the caller, so listing them is the point.
    Only a structural refusal is worth hiding."""
    card = a_card(repo)
    next_task(repo, task=card, actor=WORKER)
    update(repo, card, status="review", comment="no commit anywhere", actor=WORKER)

    assert card in {i["task"]["id"] for i in attention(repo, actor=DEV)["waiting"]}


def test_closing_a_card_tells_whoever_was_waiting_on_it(repo: Path) -> None:
    """The gap a question found: when one developer closes B and card C becomes ready, the
    STATE is right instantly — `unblock` runs in the same write, in the store everybody reads —
    and NOBODY is told. C sits pickable and invisible until somebody's next turn asks.

    The information existed and was thrown away: the close already computes which cards it
    freed and hands them to its own caller, which is the one session that does not need it.
    """
    from taskops.usecases import inbox, plan

    created = plan(repo, [{"title": "first", "spec": "s"},
                          {"title": "second", "spec": "s", "after": 0}],
                   actor="dev:ana")["created"]
    blocker, waiting = created[0]["id"], created[1]["id"]
    next_task(repo, task=blocker, actor="agent:berna/w1")

    done = update(repo, blocker, status="done", no_code=True, comment="shipped",
                  actor="dev:berna")

    assert [t["id"] for t in done["unblocked"]] == [waiting]
    assert "dev:ana" in done["notified"], "the person who planned it is told"
    said = " ".join(str(m["body"].get("text", "")) for m in inbox(repo, actor="dev:ana")["messages"])
    assert waiting in said and "is ready" in said


def test_nobody_is_told_about_their_own_close(repo: Path) -> None:
    """Telling somebody about a consequence of their own call is noise — they already got it
    in the reply. An inbox that fills with echoes is an inbox people stop opening."""
    created = plan(repo, [{"title": "first", "spec": "s"},
                          {"title": "second", "spec": "s", "after": 0}],
                   actor="dev:berna")["created"]
    next_task(repo, task=created[0]["id"], actor="agent:berna/w1")

    done = update(repo, created[0]["id"], status="done", no_code=True, comment="mine",
                  actor="dev:berna")

    assert done["unblocked"], "it did unblock something"
    assert done["notified"] == [], "and told nobody, because the only candidate was the closer"
