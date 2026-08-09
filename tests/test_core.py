"""core/ — pure, so these tests touch no disk, no clock and no network."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from taskops.core import event as ev, graph, hours, replay, review as corereview, machine, mentions
from taskops._errors import Refused, NotFound, BadRequest
from taskops.core.types import Card, Event, role_of, slugify

# ── events ──────────────────────────────────────────────────────────────────


def test_event_id_is_content_addressed_and_128_bits() -> None:
    a = ev.make("tk-aaaaaa", "dev:berna", "comment", {"text": "hi"}, 1000.0)
    b = ev.make("tk-aaaaaa", "dev:berna", "comment", {"text": "hi"}, 1000.0)
    c = ev.make("tk-aaaaaa", "dev:berna", "comment", {"text": "ho"}, 1000.0)
    assert a["id"] == b["id"] and a["id"] != c["id"]
    assert len(a["id"]) == 32 and int(a["id"], 16) >= 0


def test_verify_catches_a_tampered_line() -> None:
    good = ev.make("tk-aaaaaa", "dev:berna", "comment", {"text": "hi"}, 1000.0)
    assert ev.verify(good)
    tampered = ev.from_line(ev.to_line(good))
    tampered["body"]["text"] = "hacked"
    assert not ev.verify(tampered)


def test_line_roundtrip_keeps_unknown_body_keys() -> None:
    original = ev.make("tk-aaaaaa", "agent:berna/w1", "commit", {"sha": "a1", "subject": "x"}, 5.0)
    original["body"]["from_the_future"] = [1, 2]
    back = ev.from_line(ev.to_line(original))
    assert back == original


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kind": "nonsense", "body": {}},
        {"kind": "commit", "body": {"sha": "a1"}},  # missing 'subject'
    ],
)
def test_bad_events_are_refused_at_the_writer(kwargs: dict[str, object]) -> None:
    with pytest.raises(BadRequest):
        ev.make("tk-aaaaaa", "dev:berna", str(kwargs["kind"]), dict(kwargs["body"]), 1.0)  # type: ignore[arg-type]


def test_from_line_rejects_junk() -> None:
    for line in ("not json", "[]", '{"id":"x"}', '{"id":"x","task":"t","actor":"a","kind":"k"}'):
        with pytest.raises(BadRequest):
            ev.from_line(line)


# ── replay ──────────────────────────────────────────────────────────────────


def _card_body(ident: str, **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": ident,
        "title": ident,
        "spec": "",
        "status": "open",
        "priority": 2,
        "milestone": "ms-1",
        "after": [],
        "files": [],
        "created_by": "dev:berna",
    }
    base.update(over)
    return {"card": base}


def test_an_event_arriving_before_created_is_re_applied() -> None:
    """v1 dropped it until somebody rebuilt the cache by hand."""
    created = ev.make("tk-aaaaaa", "dev:berna", "created", _card_body("tk-aaaaaa"), 100.0)
    claimed = ev.make("tk-aaaaaa", "agent:berna/w1", "claimed", {"branch": "tk-aaaaaa"}, 90.0)
    state = replay.fold([claimed, created])
    assert state["cards"]["tk-aaaaaa"]["assignee"] == "agent:berna/w1"


def test_a_claim_records_the_owner_and_never_a_status() -> None:
    """`doing` is not storable: the process that wrote it can die, the row cannot.
    Ownership is durable; being ON it right now is the lease's answer."""
    events = [
        ev.make("tk-aaaaaa", "dev:berna", "created", _card_body("tk-aaaaaa"), 100.0),
        ev.make("tk-aaaaaa", "agent:berna/w1", "claimed", {"branch": "tk-aaaaaa"}, 110.0),
    ]
    card = replay.fold(events)["cards"]["tk-aaaaaa"]
    assert card["status"] == "open" and card["assignee"] == "agent:berna/w1"


def test_a_status_from_a_stranger_version_is_read_as_open() -> None:
    body = _card_body("tk-aaaaaa", status="doing")  # a v2-alpha log, or a newer one
    assert (
        replay.fold([ev.make("tk-aaaaaa", "dev:b", "created", body, 1.0)])["cards"]["tk-aaaaaa"][
            "status"
        ]
        == "open"
    )


def test_replay_is_idempotent_and_additive() -> None:
    events = [
        ev.make("tk-aaaaaa", "dev:berna", "created", _card_body("tk-aaaaaa"), 100.0),
        ev.make("tk-aaaaaa", "agent:berna/w1", "claimed", {"branch": "tk-aaaaaa"}, 110.0),
        ev.make("tk-aaaaaa", "agent:berna/w1", "status", {"to": "done"}, 120.0),
    ]
    once = replay.fold(list(events))
    twice = replay.fold(events + events)
    assert once == twice
    assert once["cards"]["tk-aaaaaa"]["status"] == "done"
    assert once["cards"]["tk-aaaaaa"]["assignee"] == ""


def test_events_in_the_same_instant_keep_their_arrival_order() -> None:
    """A frozen clock is the normal case in tests and a real one on a fast machine.
    Breaking the tie by event id instead made a claim land AFTER the release that
    undid it — differently on every rebuild. Twenty cards, so no single set of
    ids can pass by luck."""
    events = []
    for index in range(20):
        ident = f"tk-{index:06d}"
        events.append(ev.make(ident, "dev:berna", "created", _card_body(ident), 100.0))
        events.append(ev.make(ident, f"agent:berna/w{index}", "claimed", {"branch": ident}, 100.0))
        events.append(ev.make(ident, f"agent:berna/w{index}", "released", {"note": "back"}, 100.0))
    state = replay.fold(events)
    assert [c["status"] for c in state["cards"].values()] == ["open"] * 20
    assert not any(c["assignee"] for c in state["cards"].values())


def test_newer_wins_on_a_stale_edit() -> None:
    events = [
        ev.make("tk-aaaaaa", "dev:berna", "created", _card_body("tk-aaaaaa"), 100.0),
        ev.make("tk-aaaaaa", "dev:berna", "edited", {"field": "title", "to": "new"}, 200.0),
        ev.make("tk-aaaaaa", "dev:ana", "edited", {"field": "title", "to": "old"}, 150.0),
    ]
    assert replay.fold(events)["cards"]["tk-aaaaaa"]["title"] == "new"


def test_milestone_create_then_close() -> None:
    body = {"op": "create", "id": "ms-1", "title": "MVP", "goal": "ship", "branch": "ms/mvp"}
    close = {"op": "status", "id": "ms-1", "to": "done"}
    state = replay.fold(
        [
            ev.make("project", "dev:berna", "milestone", body, 10.0),
            ev.make("project", "dev:berna", "milestone", close, 20.0),
        ]
    )
    assert state["milestones"]["ms-1"]["branch"] == "ms/mvp"
    assert state["milestones"]["ms-1"]["status"] == "done"


def test_history_only_kinds_do_not_move_state() -> None:
    events = [
        ev.make("tk-aaaaaa", "dev:berna", "created", _card_body("tk-aaaaaa"), 100.0),
        ev.make("tk-aaaaaa", "agent:berna/w1", "comment", {"text": "note"}, 110.0),
    ]
    assert replay.fold(events)["cards"]["tk-aaaaaa"]["updated"] == 100.0


# ── machine ─────────────────────────────────────────────────────────────────


def _card(**over: object) -> Card:
    base: dict[str, object] = {
        "id": "tk-aaaaaa",
        "title": "t",
        "spec": "",
        "status": "open",
        "priority": 2,
        "milestone": "ms-1",
        "parent": None,
        "after": [],
        "files": [],
        "assignee": "",
        "created_by": "dev:berna",
        "created": 1.0,
        "updated": 1.0,
    }
    base.update(over)
    return Card(**base)  # type: ignore[typeddict-item]


def test_take_refused_when_held_by_somebody_else() -> None:
    facts = machine.Facts("open", "agent:berna/w1", "agent:berna/w1", 0)
    with pytest.raises(Refused, match="held by agent:berna/w1"):
        machine.check_take(_card(), facts, "agent:berna/w2")


def test_done_without_a_commit_names_the_honest_way_out() -> None:
    facts = machine.Facts("open", "agent:berna/w1", "agent:berna/w1", 0)
    with pytest.raises(Refused, match="no_code=true"):
        machine.check_transition(_card(), facts, "agent:berna/w1", "done")
    machine.check_transition(
        _card(), facts, "agent:berna/w1", "done", no_code=True, has_comment=True
    )
    machine.check_transition(_card(), machine.Facts("open", "", None, 1), "dev:b", "done")


def test_a_lapsed_lease_does_not_cost_you_your_own_card() -> None:
    """Twenty quiet minutes editing must not end with the board refusing to let
    you close what you just built."""
    gone = machine.Facts("open", "agent:berna/w1", None, 1)  # its own lease expired
    machine.check_transition(_card(), gone, "agent:berna/w1", "done")
    taken = machine.Facts("open", "agent:berna/w2", "agent:berna/w2", 1)
    with pytest.raises(Refused, match="took it over"):
        machine.check_transition(_card(), taken, "agent:berna/w1", "done")


def test_doing_is_not_a_status_anybody_can_write() -> None:
    with pytest.raises(BadRequest, match="not written"):
        machine.check_transition(_card(), machine.Facts("open", "", None, 0), "dev:b", "doing")


def test_dropping_needs_a_reason_and_release_needs_a_note() -> None:
    with pytest.raises(Refused, match="needs a reason"):
        machine.check_transition(_card(), machine.Facts("open", "", None, 0), "dev:b", "dropped")
    with pytest.raises(Refused, match="next worker"):
        machine.check_release(
            _card(), machine.Facts("open", "agent:berna/w1", None, 0), "agent:berna/w1", ""
        )


# ── graph ───────────────────────────────────────────────────────────────────


def _two() -> dict[str, Card]:
    return {
        "tk-aaaaaa": _card(id="tk-aaaaaa"),
        "tk-bbbbbb": _card(id="tk-bbbbbb", after=["tk-aaaaaa"]),
    }


def test_blocked_becomes_ready_when_the_blocker_closes_with_no_writer() -> None:
    cards = _two()
    assert graph.derived(cards, cards["tk-bbbbbb"]) == "blocked"
    cards["tk-aaaaaa"]["status"] = "done"
    assert graph.derived(cards, cards["tk-bbbbbb"]) == "ready"
    assert [c["id"] for c in graph.ready(cards)] == ["tk-bbbbbb"]


def test_the_state_shown_comes_from_who_holds_the_lease() -> None:
    """The whole point: `doing` is a live fact, so it ends by itself."""
    cards = _two()
    card = cards["tk-aaaaaa"]
    card["assignee"] = "agent:berna/w1"

    held = {"tk-aaaaaa": "agent:berna/w1"}
    assert graph.derived(cards, card, held) == "doing"
    assert graph.ready(cards, held) == []

    # the worker dies: nothing is written, the lease simply stops existing
    assert graph.derived(cards, card, {}) == "stalled"
    assert graph.mine(cards, "agent:berna/w1", {})[0]["id"] == "tk-aaaaaa"
    assert graph.ready(cards, {}) == []  # still not up for grabs: it has an owner


def test_a_card_nobody_owns_is_ready() -> None:
    cards = _two()
    assert graph.derived(cards, cards["tk-aaaaaa"], {}) == "ready"


def test_a_cycle_is_refused_at_the_write() -> None:
    cards = _two()
    with pytest.raises(Refused, match="cycle"):
        graph.check_dep(cards, "tk-aaaaaa", "tk-bbbbbb")
    with pytest.raises(Refused, match="itself"):
        graph.check_dep(cards, "tk-aaaaaa", "tk-aaaaaa")
    with pytest.raises(NotFound):
        graph.check_dep(cards, "tk-aaaaaa", "tk-zzzzzz")


def test_ready_is_urgent_first_then_oldest() -> None:
    cards = {
        "tk-111111": _card(id="tk-111111", priority=2, created=1.0),
        "tk-222222": _card(id="tk-222222", priority=0, created=9.0),
        "tk-333333": _card(id="tk-333333", priority=2, created=0.5),
    }
    assert [c["id"] for c in graph.ready(cards)] == ["tk-222222", "tk-333333", "tk-111111"]


# ── mentions ────────────────────────────────────────────────────────────────

W1 = "agent:berna/w1"
BERNA = "dev:berna"


def _thread(*events: Event) -> dict[str, list[Event]]:
    grouped: dict[str, list[Event]] = {}
    for event in events:
        grouped.setdefault(event["task"], []).append(event)
    return grouped


def _mention(task: str, by: str, who: list[str], ts: float, text: str = "look at this") -> Event:
    return ev.make(task, by, "comment", {"text": text, "mentions": who}, ts)


def test_a_mention_is_pending_until_the_actor_touches_that_card() -> None:
    """THE behaviour the whole design rests on: nothing is written to clear it.

    The mentioned actor answers on the card and the mention resolves itself —
    no `read` flag, no ack verb, nothing that could survive being wrong.
    """
    said = _mention("tk-aaaaaa", W1, [BERNA], 100.0)
    assert [m["task"] for m in mentions.pending(_thread(said), BERNA)] == ["tk-aaaaaa"]

    answered = ev.make("tk-aaaaaa", BERNA, "comment", {"text": "use Decimal"}, 200.0)
    assert mentions.pending(_thread(said, answered), BERNA) == []


def test_an_earlier_event_by_the_actor_does_not_clear_a_later_mention() -> None:
    """The trap: "has this actor ever spoken here" is not the question."""
    before = ev.make("tk-aaaaaa", BERNA, "comment", {"text": "planning"}, 50.0)
    said = _mention("tk-aaaaaa", W1, [BERNA], 100.0)
    assert len(mentions.pending(_thread(before, said), BERNA)) == 1


def test_somebody_elses_answer_is_not_yours() -> None:
    said = _mention("tk-aaaaaa", W1, [BERNA], 100.0)
    other = ev.make("tk-aaaaaa", "agent:berna/w2", "comment", {"text": "not me"}, 200.0)
    assert len(mentions.pending(_thread(said, other), BERNA)) == 1
    assert mentions.pending(_thread(said, other), "agent:berna/w2") == []


def test_any_kind_of_event_by_the_actor_clears_it_not_only_a_comment() -> None:
    """Claiming the card IS reading the thread: `take` returns the whole of it."""
    said = _mention("tk-aaaaaa", BERNA, [W1], 100.0)
    claimed = ev.make("tk-aaaaaa", W1, "claimed", {"branch": "tk-aaaaaa"}, 200.0)
    assert mentions.pending(_thread(said, claimed), W1) == []


def test_a_closed_card_owes_nobody_a_reply() -> None:
    said = _mention("tk-aaaaaa", W1, [BERNA], 100.0)
    threads = _thread(said)
    assert len(mentions.pending(threads, BERNA)) == 1
    assert mentions.pending(threads, BERNA, {"tk-aaaaaa"}) == []


def test_only_the_named_actor_sees_it_and_the_body_carries_who_wrote_it() -> None:
    said = _mention("tk-aaaaaa", W1, [BERNA, "agent:berna/w2"], 100.0, text="two of you")
    got = mentions.pending(_thread(said), BERNA)
    assert got == [{"task": "tk-aaaaaa", "by": W1, "text": "two of you", "ts": 100.0}]
    assert mentions.pending(_thread(said), "agent:berna/w3") == []


def test_only_a_comment_addresses_anybody() -> None:
    """A `comment` is the one home for this. A `mentions` key on any other kind
    is an extra from somewhere else, kept intact by `make()` and read by nobody
    — two homes for "who must read this" is how a fact starts drifting."""
    plain = ev.make("tk-aaaaaa", W1, "comment", {"text": "note to the thread"}, 100.0)
    wrong_shape = ev.make("tk-bbbbbb", W1, "comment", {"text": "x", "mentions": BERNA}, 101.0)
    wrong_kind = ev.make("tk-cccccc", W1, "released", {"note": "x", "mentions": [BERNA]}, 102.0)
    assert mentions.pending(_thread(plain, wrong_shape, wrong_kind), BERNA) == []


def test_mentions_are_per_card_and_oldest_first() -> None:
    late = _mention("tk-bbbbbb", W1, [BERNA], 300.0, text="second")
    early = _mention("tk-aaaaaa", W1, [BERNA], 100.0, text="first")
    answered_elsewhere = ev.make("tk-bbbbbb", BERNA, "comment", {"text": "on b"}, 200.0)
    got = mentions.pending(_thread(late, early, answered_elsewhere), BERNA)
    assert [m["text"] for m in got] == ["first", "second"]


def test_a_tie_on_the_timestamp_keeps_arrival_order() -> None:
    """A frozen clock, or two events in the same second: the answer must still
    count as an answer. `replay` settles simultaneity the same way — stable
    sort, arrival order — and this had to agree with it."""
    said = _mention("tk-aaaaaa", W1, [BERNA], 100.0)
    answered = ev.make("tk-aaaaaa", BERNA, "comment", {"text": "ok"}, 100.0)
    assert mentions.pending(_thread(said, answered), BERNA) == []


# ── hours ───────────────────────────────────────────────────────────────────


def test_a_long_gap_is_dropped_not_capped() -> None:
    """v1 capped at 30m and added a phantom half hour per session break."""
    stamps = [(0.0, "tk-a"), (600.0, "tk-a"), (100_000.0, "tk-b"), (100_300.0, "tk-b")]
    got = hours.spent(stamps)
    assert got == {"tk-a": 600.0, "tk-b": 300.0}
    assert hours.total(stamps) == 900.0


def test_sessions_are_runs_of_intervals_and_a_dropped_gap_breaks_them() -> None:
    """A block is a RUN — consecutive counted intervals on one card merge — and
    what breaks it is a dropped gap or a change of card, never a tick."""
    stamps = [
        (0.0, "tk-a"),
        (300.0, "tk-a"),  # merges into the block that started at 0
        (900.0, "tk-a"),
        (100_000.0, "tk-a"),  # the gap before it is > GAP: dropped whole, and
        (100_300.0, "tk-a"),  # the SAME card does not heal over it
        (100_600.0, "tk-c"),  # touching, but another card: its own block
    ]
    got = hours.sessions(stamps)
    assert [(s["start"], s["end"], s["task"], s["seconds"]) for s in got] == [
        (0.0, 900.0, "tk-a", 900.0),
        (100_000.0, 100_300.0, "tk-a", 300.0),
        (100_300.0, 100_600.0, "tk-c", 300.0),
    ]
    # The wall-clock between two blocks is time NOBODY counted — it is what the
    # timesheet draws as space, and it is not in any session.
    assert got[1]["start"] - got[0]["end"] == 99_100.0


def test_spent_is_a_fold_of_sessions_and_nothing_else() -> None:
    """One definition of an interval: the totals ARE the blocks, summed."""
    stamps = [(0.0, "tk-a"), (600.0, "tk-a"), (100_000.0, "tk-b"), (100_300.0, "tk-b")]
    folded: dict[str, float] = {}
    for block in hours.sessions(stamps):
        folded[block["task"]] = folded.get(block["task"], 0.0) + block["seconds"]
    assert hours.spent(stamps) == folded
    assert hours.total(stamps) == sum(s["seconds"] for s in hours.sessions(stamps))


def test_a_dst_day_is_not_24_hours() -> None:
    tz = "Europe/Madrid"
    when = datetime(2026, 3, 30, 12, 0, tzinfo=ZoneInfo(tz)).timestamp()
    got = {day: end - start for day, start, end in hours.windows(when, tz, 2)}
    assert got["2026-03-29"] == 23 * 3600.0  # spring forward
    assert got["2026-03-30"] == 24 * 3600.0


def test_day_bounds_contain_their_own_timestamp() -> None:
    when = datetime(2026, 8, 5, 23, 30, tzinfo=ZoneInfo("Europe/Madrid")).timestamp()
    start, end = hours.day_bounds(when, "Europe/Madrid")
    assert start <= when < end


def test_human_reads_like_a_person_wrote_it() -> None:
    assert hours.human(0) == "—"
    assert hours.human(35 * 60) == "35m"
    assert hours.human(2 * 3600) == "2h"
    assert hours.human(2 * 3600 + 40 * 60) == "2h 40m"


# ── actor grammar ───────────────────────────────────────────────────────────


def test_role_is_derived_from_the_actor_grammar() -> None:
    assert role_of("dev:berna") == "dev"
    assert role_of("agent:berna/w1") == "agent"
    assert role_of("taskops") == "system"


@pytest.mark.parametrize("bad", ["berna", "agent:berna", "dev:", "who:x", "dev:Berna", "agent:/w"])
def test_a_malformed_actor_names_the_export_line(bad: str) -> None:
    with pytest.raises(BadRequest):
        role_of(bad)


def test_slug_is_stable_and_bounded() -> None:
    assert slugify("MVP facturador") == "mvp-facturador"
    assert slugify("  ¡Qué!  ") == "qu"
    assert len(slugify("x" * 80)) == 32


# ── review (optional) ───────────────────────────────────────────────────────

R1 = "agent:berna/r1"


def _submitted(task: str, by: str, ts: float, note: str = "done") -> Event:
    return ev.make(task, by, "submitted", {"note": note}, ts)


def _reviewed(task: str, by: str, verdict: str, ts: float, note: str = "why") -> Event:
    return ev.make(task, by, "reviewed", {"verdict": verdict, "note": note}, ts)


def test_a_card_never_handed_in_has_no_standing() -> None:
    assert corereview.standing([_reviewed("tk-aaaaaa", R1, "pass", 10.0)]) == corereview.EMPTY
    assert corereview.pending(_thread(_submitted("tk-aaaaaa", W1, 10.0))) != {}


def test_a_verdict_older_than_the_last_submission_is_stale() -> None:
    """Resubmitting ANSWERS the previous verdict — there is nothing to clear.

    The round is opened by the last `submitted` and only a `reviewed` after it
    counts, so a card whose worker handed it in again is waiting for a verdict,
    never carrying the old one.
    """
    events = [
        _submitted("tk-aaaaaa", W1, 10.0),
        _reviewed("tk-aaaaaa", R1, "changes", 20.0, "rounding is wrong"),
        _submitted("tk-aaaaaa", W1, 30.0, "fixed the rounding"),
    ]
    stood = corereview.standing(events)
    assert stood.verdict == "" and stood.note == ""
    assert stood.submitted_at == 30.0 and stood.submitted_by == W1

    # and the verdict that comes AFTER it is the one that counts
    stood = corereview.standing([*events, _reviewed("tk-aaaaaa", R1, "pass", 40.0, "good")])
    assert (stood.verdict, stood.verdict_by, stood.note) == ("pass", R1, "good")


def test_a_review_tie_on_the_timestamp_keeps_arrival_order() -> None:
    """The clock in this suite is frozen, and in production it is coarse.

    Compared by timestamp VALUE a verdict written in the same instant as the
    resubmission that answers it would outrank it, and the round would survive
    its own verdict. Position in a stable sort is what settles simultaneity —
    the same rule `mentions.pending` and `replay` already follow.
    """
    same = 10.0
    # verdict first, then a resubmission in the same instant: the round reopens
    stood = corereview.standing(
        [
            _submitted("tk-aaaaaa", W1, same),
            _reviewed("tk-aaaaaa", R1, "changes", same, "no"),
            _submitted("tk-aaaaaa", W1, same, "again"),
        ]
    )
    assert stood.verdict == "" and stood.note == ""
    # the mirror image: the verdict arrives last, so it answers the submission
    stood = corereview.standing(
        [
            _submitted("tk-aaaaaa", W1, same),
            _submitted("tk-aaaaaa", W1, same, "again"),
            _reviewed("tk-aaaaaa", R1, "changes", same, "no"),
        ]
    )
    assert stood.verdict == "changes"


def test_review_states_follow_the_documented_precedence() -> None:
    """The documented precedence of the review states, every row, in order.

    Two placements look wrong if you skim and are deliberate: `review` sits
    ABOVE `doing` (a submitted card whose worker is still alive is waiting for a
    reviewer), and `changes` sits BELOW it (a worker back on the card is
    working, not waiting).
    """
    held = {"tk-bbbbbb": W1}
    checking = {"tk-bbbbbb": R1}
    waiting = {"tk-bbbbbb": corereview.Standing(10.0, W1, "", "", "")}
    changes = {"tk-bbbbbb": corereview.Standing(10.0, W1, "changes", R1, "fix it")}

    def state(**over: object) -> str:
        cards = _two()
        card = cards["tk-bbbbbb"]
        card["review"] = True
        card["after"] = list(over.pop("after", []))  # type: ignore[arg-type]
        card["assignee"] = str(over.pop("assignee", ""))
        card["status"] = str(over.pop("status", "open"))
        return graph.derived(
            cards,
            card,
            over.pop("holders", None),  # type: ignore[arg-type]
            over.pop("reviewing", None),  # type: ignore[arg-type]
            over.pop("standings", None),  # type: ignore[arg-type]
        )

    # done | dropped first, whatever else is true
    assert state(status="done", holders=held, reviewing=checking, standings=waiting) == "done"
    # reviewing beats everything open — somebody is on it RIGHT NOW
    assert state(holders=held, reviewing=checking, standings=waiting) == "reviewing"
    # review ABOVE doing: handed in, nobody judging, worker still alive
    assert state(holders=held, standings=waiting) == "review"
    # doing ABOVE changes: the worker picked it back up
    assert state(holders=held, standings=changes) == "doing"
    # changes, once nobody is on it
    assert state(standings=changes) == "changes"
    # changes ABOVE blocked and stalled: the move is the same either way
    assert state(standings=changes, after=["tk-aaaaaa"], assignee=W1) == "changes"
    assert state(after=["tk-aaaaaa"]) == "blocked"
    assert state(assignee=W1) == "stalled"
    assert state() == "ready"


def test_a_card_without_review_derives_exactly_as_before() -> None:
    """THE optionality test: a board that never sets `review` is unchanged.

    Same inputs, same answers — and the two new parameters carry the review
    facts of OTHER cards without touching this one.
    """
    cards = _two()
    card = cards["tk-aaaaaa"]
    stood = {"tk-bbbbbb": corereview.Standing(10.0, W1, "changes", R1, "not this card")}
    for holders, expected in (({}, "ready"), ({"tk-aaaaaa": W1}, "doing")):
        assert graph.derived(cards, card, holders) == expected
        assert graph.derived(cards, card, holders, {}, stood) == expected
    # even handed in and judged, a card that does not require review is not held
    # back by it: `review` is the flag, and it is off.
    mine = {"tk-aaaaaa": corereview.Standing(10.0, W1, "changes", R1, "fix")}
    assert graph.derived(cards, card, {}, {}, mine) == "ready"
    machine.check_transition(_card(), machine.Facts("open", "", None, 1), "dev:b", "done")


def test_a_card_that_requires_review_cannot_be_closed_without_a_pass() -> None:
    card = _card(review=True)
    handed = machine.Facts("open", W1, W1, 1, corereview.Standing(10.0, W1, "", "", ""))
    with pytest.raises(Refused, match="status=review"):
        machine.check_transition(card, handed, W1, "done")
    passed = machine.Facts("open", W1, W1, 1, corereview.Standing(10.0, W1, "pass", R1, "ok"))
    machine.check_transition(card, passed, W1, "done")
    # and the orchestrator may close it even while the worker's lease is live —
    # the worker deliberately stays reachable after handing in.
    machine.check_transition(card, passed, "dev:berna", "done")
    with pytest.raises(Refused, match="held by"):
        machine.check_transition(card, handed, "dev:berna", "done")


def test_a_project_fact_is_newest_wins_however_the_log_arrives() -> None:
    """A project fact has no card, so it has no `updated` to arbitrate with —
    property 3 of `replay` has to hold through `project_at` instead.

    The INCREMENTAL fold is what needs it: `Stores.state()` applies whatever is
    new in the cache on top of a state it already holds, in seq order, and seq
    order is arrival order — an older event written by another clone arrives
    after the newer one it must not resurrect. A single `fold` sorts by ts and
    would never notice."""
    old = ev.make("project", "dev:berna", "project", {"op": "remote", "value": {"slug": "a/b"}}, 1000.0)
    new = ev.make("project", "dev:berna", "project", {"op": "remote", "value": {"slug": "c/d"}}, 2000.0)
    state = replay.fold([new])
    replay.fold([old], state)  # a second pass, the way Stores.state() applies it
    assert state["project"]["remote"] == {"slug": "c/d"}
    assert state["project"] == replay.fold([old, new])["project"]


def test_a_project_fact_never_lands_on_a_card() -> None:
    """It is board-level by construction: nothing in `cards` moves, and a board
    that never recorded one has an empty dict, not a missing key."""
    state = replay.fold([ev.make("project", "dev:berna", "project", {"op": "remote", "value": None}, 1000.0)])
    assert state["cards"] == {} and state["project"] == {"remote": None}
    assert replay.empty()["project"] == {}
