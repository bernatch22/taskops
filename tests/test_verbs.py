"""A card's whole life (ARCHITECTURE.md §8), against a local board.

plan → dispatch → take → commit → done → merge, plus the two ugly cases
(a dead worker, a lost race) and the role wall in both directions.
"""

from __future__ import annotations

import json
from typing import Any, Callable

import pytest

from taskops import verbs, _clock
from taskops.core import seams
from taskops.store import log
from taskops.verbs import pulse, _facts, project, _stories
from taskops._errors import Refused, NotFound, BadRequest
from taskops.core.types import ANON, LEASE_TTL
from taskops.store.stores import Stores

BERNA = "dev:berna"
W1 = "agent:berna/w1"
W2 = "agent:berna/w2"

pytestmark = pytest.mark.usefixtures("clock")


def call(stores: Stores, verb: str, actor: str, **args: Any) -> dict[str, Any]:
    return verbs.call(stores, verb, actor, args)


def planned(stores: Stores) -> dict[str, Any]:
    """The five cards of the worked example, with the same dependencies."""
    return call(
        stores,
        "plan",
        BERNA,
        milestone="MVP facturador",
        goal="read a bank CSV and issue invoices with VAT",
        tasks=[
            {"title": "invoice model", "spec": "the Invoice dataclass", "files": ["src/models.py"]},
            {"title": "CSV parser", "spec": "read the bank export", "files": ["src/parser.py"]},
            {"title": "VAT", "spec": "compute it", "files": ["src/tax.py"], "after": 0},
            {"title": "PDF export", "spec": "render it", "files": ["src/pdf.py"], "after": 0},
            {"title": "load CLI", "spec": "wire it", "files": ["src/cli.py"], "after": 1},
        ],
    )


# ── planning ────────────────────────────────────────────────────────────────


def test_plan_writes_the_tree_and_stores_the_branch(stores: Stores) -> None:
    out = planned(stores)
    assert out["milestone"]["branch"] == "ms/mvp-facturador"
    assert len(out["cards"]) == 5
    board = call(stores, "board", BERNA)
    assert [c["title"] for c in board["groups"]["take"]] == ["invoice model", "CSV parser"]
    assert len(board["groups"]["blocked"]) == 3


def test_renaming_a_milestone_never_moves_its_branch(stores: Stores) -> None:
    """v1 re-derived the branch from a mutable title and grew ghost branches."""
    out = planned(stores)
    ident = out["milestone"]["id"]
    call(stores, "update", BERNA, milestone=ident, title="MVP facturación")
    assert stores.state()["milestones"][ident]["branch"] == "ms/mvp-facturador"


def test_landing_a_milestone_closes_it(stores: Stores) -> None:
    """Landing IS closing. The `landed` op used to fall through the fold
    unfolded: the chapter stayed "open" forever, and from the second chapter on
    `open_milestone` (None for "several") could never focus one again — no
    Chapter pane, `plan` demanding milestone= on every call, permanently.
    Found on the first real landing, 2026-08-07."""
    ident = planned(stores)["milestone"]["id"]
    call(stores, "merged", BERNA, milestone=ident, into="master", sha="abc123")
    assert stores.state()["milestones"][ident]["status"] == "landed"
    # And the board can focus a fresh chapter again — the symptom that exposed it.
    second = call(stores, "plan", BERNA, milestone="chapter two", goal="g", tasks=[{"title": "t"}])
    board = call(stores, "board", BERNA)
    assert board["milestone"] is not None
    assert board["milestone"]["id"] == second["milestone"]["id"]


def test_a_new_chapter_is_warned_about_the_unlanded_one_it_will_not_see(stores: Stores) -> None:
    """The Monitor chapter was cut from a `master` missing 27 commits of unlanded
    UI work; a worker found out when its worktree had no `ui/` at all. A warning,
    never a refusal — opening a second chapter deliberately is normal."""
    first = planned(stores)["milestone"]
    second = call(stores, "plan", BERNA, milestone="Monitor", goal="g", tasks=[{"title": "t"}])
    assert second["cards"], "the plan still went through — this is a warning, not a refusal"
    note = "\n".join(second["notes"])
    assert f'{first["id"]} "MVP facturador" is open and has not landed.' in note
    assert "ms/monitor is cut from the trunk, so it will not see that chapter's work." in note


def test_a_landed_chapter_is_not_warned_about(stores: Stores) -> None:
    ident = planned(stores)["milestone"]["id"]
    call(stores, "merged", BERNA, milestone=ident, into="master", sha="abc123")
    assert call(stores, "plan", BERNA, milestone="Monitor", tasks=[{"title": "t"}])["notes"] == []


def test_a_dropped_chapter_is_not_warned_about(stores: Stores) -> None:
    ident = planned(stores)["milestone"]["id"]
    call(stores, "update", BERNA, milestone=ident, status="dropped")
    assert call(stores, "plan", BERNA, milestone="Monitor", tasks=[{"title": "t"}])["notes"] == []


def test_a_finished_but_unlanded_chapter_is_still_warned_about(stores: Stores) -> None:
    """`done` is not `landed`: the work exists on a branch the trunk does not
    carry, which is exactly what the new branch will not see."""
    ident = planned(stores)["milestone"]["id"]
    call(stores, "update", BERNA, milestone=ident, status="done")
    out = call(stores, "plan", BERNA, milestone="Monitor", tasks=[{"title": "t"}])
    assert f'{ident} "MVP facturador" is done and has not landed.' in out["notes"]


def test_adding_cards_to_an_existing_chapter_warns_about_nothing(stores: Stores) -> None:
    """The warning is about the branch a NEW chapter is cut from. Planning into a
    chapter that already exists cuts no branch, so there is nothing to say."""
    first = planned(stores)["milestone"]
    call(stores, "plan", BERNA, milestone="Monitor", goal="g", tasks=[{"title": "t"}])
    by_id = call(stores, "plan", BERNA, milestone=first["id"], tasks=[{"title": "more"}])
    assert by_id["notes"] == []
    by_title = call(stores, "plan", BERNA, milestone="MVP facturador", tasks=[{"title": "yet"}])
    assert by_title["notes"] == []


def test_planning_the_same_title_twice_adds_to_the_same_milestone(stores: Stores) -> None:
    """Two chapters with one name would split the board: two goals, two branches,
    and two possible answers to "the open milestone"."""
    first = planned(stores)["milestone"]["id"]
    again = call(
        stores,
        "plan",
        BERNA,
        milestone="MVP facturador",
        goal="ignored — the chapter already has one",
        tasks=[{"title": "one more"}],
    )
    assert again["milestone"]["id"] == first
    assert len(stores.state()["milestones"]) == 1
    assert len(stores.state()["cards"]) == 6


def test_a_dependency_cycle_is_refused_at_the_write(stores: Stores) -> None:
    with pytest.raises(Refused, match="cycle"):
        call(
            stores,
            "plan",
            BERNA,
            milestone="loop",
            goal="…",
            tasks=[
                {"title": "a", "after": 1},
                {"title": "b", "after": 0},
            ],
        )


def test_an_index_outside_the_batch_is_a_bad_request(stores: Stores) -> None:
    with pytest.raises(BadRequest, match="outside this call"):
        call(stores, "plan", BERNA, milestone="m", goal="g", tasks=[{"title": "a", "after": 3}])


# ── the role wall ───────────────────────────────────────────────────────────


def test_the_orchestrator_cannot_hold_a_card(stores: Stores) -> None:
    out = planned(stores)
    with pytest.raises(Refused, match="taskops_assign"):
        call(stores, "take", BERNA, task=out["cards"][0]["id"])


def test_a_worker_cannot_plan_or_dispatch_or_merge(stores: Stores) -> None:
    planned(stores)
    for verb, hint in (("plan", "do not plan"), ("assign", "orchestrator"), ("merged", "workers")):
        with pytest.raises(Refused, match=hint):
            call(stores, verb, W1, tasks=[])


def test_an_unknown_verb_lists_the_ones_that_exist(stores: Stores) -> None:
    with pytest.raises(BadRequest, match="this board answers"):
        call(stores, "land", BERNA)


# ── dispatch and take ───────────────────────────────────────────────────────


def test_dispatch_names_workers_and_takes_the_cards_out_of_the_pool(stores: Stores) -> None:
    cards = planned(stores)["cards"]
    out = call(stores, "assign", BERNA, tasks=[cards[0]["id"], cards[1]["id"]])
    assert [b["actor"] for b in out["briefs"]] == [W1, W2]
    assert out["briefs"][0]["base"] == "ms/mvp-facturador"  # the worktree is cut from here
    assert out["briefs"][0]["worktree"] == f".taskops/trees/{cards[0]['id']}"
    assert call(stores, "board", BERNA)["groups"]["take"] == []


def test_a_dispatched_card_is_visible_before_its_worker_arrives(stores: Stores) -> None:
    """Between dispatch and the first take the card belonged to no group at all,
    so the board read as empty with work in flight. It is owned and nobody is
    running it — which IS stalled, and the move is the same either way: hand it
    to somebody."""
    cards = planned(stores)["cards"]
    call(stores, "assign", BERNA, tasks=[cards[0]["id"]])
    board = call(stores, "board", BERNA)
    rows = board["groups"]["stalled"]
    assert [r["id"] for r in rows] == [cards[0]["id"]]
    assert rows[0]["assignee"] == W1 and rows[0]["holder"] is None
    assert board["pulse"]["counts"]["stalled"] == 1


def test_take_returns_the_goal_the_spec_and_the_worktree(stores: Stores) -> None:
    cards = planned(stores)["cards"]
    call(stores, "assign", BERNA, tasks=[cards[0]["id"]])
    got = call(stores, "take", W1, task=cards[0]["id"])
    assert got["milestone"]["goal"] == "read a bank CSV and issue invoices with VAT"
    assert got["card"]["spec"] == "the Invoice dataclass"
    assert got["branch"] == cards[0]["id"] and got["worktree"].endswith(cards[0]["id"])
    # `doing` is the LEASE, not a row: the stored status stays `open`.
    assert got["state"] == "doing" and got["card"]["status"] == "open"


def test_two_workers_one_card_and_the_loser_is_told_where_to_look(stores: Stores) -> None:
    cards = planned(stores)["cards"]
    call(stores, "take", W1, task=cards[0]["id"])
    with pytest.raises(Refused, match="held by agent:berna/w1"):
        call(stores, "take", W2, task=cards[0]["id"])


def test_a_worker_with_nothing_assigned_takes_from_the_pool(stores: Stores) -> None:
    planned(stores)
    got = call(stores, "take", W1)
    assert got["card"]["title"] == "invoice model"


def test_capture_creates_and_claims_in_one_call(stores: Stores) -> None:
    planned(stores)
    got = call(stores, "take", W1, title="fix the import", spec="found while working")
    assert got["state"] == "doing" and got["card"]["assignee"] == W1
    assert got["card"]["title"] == "fix the import"


# ── closing ─────────────────────────────────────────────────────────────────


def test_done_needs_a_commit_and_bind_provides_it(
    stores: Stores, clock: Callable[[float], None]
) -> None:
    card = planned(stores)["cards"][0]["id"]
    call(stores, "take", W1, task=card)
    with pytest.raises(Refused, match="no commit bound"):
        call(stores, "update", W1, task=card, status="done", comment="ready")
    call(
        stores, "bind", W1, task=card, sha="a1b2c3", subject="feat: model", files=["src/models.py"]
    )
    clock(60)
    out = call(stores, "update", W1, task=card, status="done", comment="model + tests")
    assert out["card"]["status"] == "done"


def test_no_code_is_the_honest_exit(stores: Stores) -> None:
    card = planned(stores)["cards"][0]["id"]
    call(stores, "take", W1, task=card)
    out = call(
        stores, "update", W1, task=card, status="done", no_code=True, comment="already fixed"
    )
    assert out["card"]["status"] == "done"


def test_closing_a_blocker_frees_its_dependents_with_no_writer(stores: Stores) -> None:
    cards = planned(stores)["cards"]
    call(stores, "take", W1, task=cards[0]["id"])
    call(stores, "update", W1, task=cards[0]["id"], status="done", no_code=True, comment="done")
    take = [c["title"] for c in call(stores, "board", BERNA)["groups"]["take"]]
    assert "VAT" in take and "PDF export" in take


def test_release_leaves_a_note_the_next_worker_is_shown(stores: Stores) -> None:
    """v1 recorded this and never displayed it; every worker started cold."""
    card = planned(stores)["cards"][0]["id"]
    call(stores, "take", W1, task=card)
    with pytest.raises(Refused, match="next worker"):
        call(stores, "update", W1, task=card, status="released")
    call(stores, "update", W1, task=card, status="released", comment="got to rounding, tax left")
    got = call(stores, "take", W2, task=card)
    assert got["resume"] == "got to rounding, tax left"


def test_a_closing_comment_appears_once_not_twice(stores: Stores) -> None:
    """The note IS the status event's body; a separate comment event put the same
    sentence in the thread twice."""
    card = planned(stores)["cards"][0]["id"]
    call(stores, "take", W1, task=card)
    call(stores, "update", W1, task=card, status="released", comment="hasta el redondeo")
    thread = [e for e in stores.events(card) if e["kind"] in ("comment", "released")]
    assert [e["kind"] for e in thread] == ["released"]
    assert thread[0]["body"]["note"] == "hasta el redondeo"


def test_dropping_demands_a_reason(stores: Stores) -> None:
    card = planned(stores)["cards"][0]["id"]
    with pytest.raises(Refused, match="needs a reason"):
        call(stores, "update", BERNA, task=card, status="dropped")
    out = call(stores, "update", BERNA, task=card, status="dropped", comment="obsolete")
    assert out["card"]["status"] == "dropped"


# ── integration ─────────────────────────────────────────────────────────────


def test_merge_only_accepts_done_cards_and_clears_the_merge_group(stores: Stores) -> None:
    card = planned(stores)["cards"][0]["id"]
    call(stores, "take", W1, task=card)
    with pytest.raises(Refused, match="not done"):
        call(stores, "merged", BERNA, task=card, sha="9c2f")
    call(stores, "update", W1, task=card, status="done", no_code=True, comment="done")
    assert [c["id"] for c in call(stores, "board", BERNA)["groups"]["merge"]] == [card]
    out = call(stores, "merged", BERNA, task=card, sha="9c2f")
    assert out["into"] == "ms/mvp-facturador"
    assert call(stores, "board", BERNA)["groups"]["merge"] == []


def test_an_integrated_card_stays_visible_under_done(stores: Stores) -> None:
    """A merged card used to leave the payload entirely: it was in no group and
    on no screen, so a chapter's finished work existed only in the event log.
    21 closed cards and nothing to show for them (2026-08-07)."""
    card = planned(stores)["cards"][0]["id"]
    call(stores, "take", W1, task=card)
    call(stores, "update", W1, task=card, status="done", no_code=True, comment="done")
    call(stores, "merged", BERNA, task=card, sha="9c2f")
    board = call(stores, "board", BERNA)
    assert board["groups"]["merge"] == []  # integrated: nothing left to do
    assert [c["id"] for c in board["groups"]["done"]] == [card]  # but still visible
    assert board["done_total"] == 1


def test_a_landed_chapter_is_still_on_the_board(stores: Stores) -> None:
    """The same bug as `done`, one level up: `milestones` filtered to `open`,
    which was correct until `landed` became a real status — and the day it did,
    two finished chapters (14 cards and 22) were in the log and on no screen.
    Berna found both by looking at the dashboard."""
    stone = planned(stores)["milestone"]["id"]
    call(stores, "merged", BERNA, milestone=stone, into="main", sha="9c2f")

    board = call(stores, "board", BERNA)
    listed = {m["id"]: m["status"] for m in board["milestones"]}
    assert listed == {stone: "landed"}
    assert board["landed_total"] == 1

    # And it RESOLVES when named — a chapter offered by a picker the server then
    # refused to focus would be the same hole with an extra click in it.
    focused = call(stores, "board", BERNA, milestone=stone)
    assert focused["milestone"]["id"] == stone
    assert focused["milestone"]["goal"] == "read a bank CSV and issue invoices with VAT"


def test_the_landed_chapters_are_capped_newest_first(
    stores: Stores, clock: Callable[[float], None]
) -> None:
    """Open chapters are bounded by the work in flight; landed ones only grow.
    Same argument as `DONE_SHOWN`, so the same shape: a cap, newest first, and
    the honest total beside it."""
    landed = []
    start = _clock.now()
    for n in range(_facts.LANDED_SHOWN + 2):
        clock(start + n * 86400)  # a chapter is days apart, never the same instant
        out = call(stores, "plan", BERNA, milestone=f"chapter {n}", goal="g", tasks=[{"title": "t"}])
        landed.append(out["milestone"]["id"])
        call(stores, "merged", BERNA, milestone=landed[-1], into="main", sha="9c2f")

    board = call(stores, "board", BERNA)
    assert board["landed_total"] == _facts.LANDED_SHOWN + 2
    shown = [m["id"] for m in board["milestones"]]
    assert len(shown) == _facts.LANDED_SHOWN
    assert shown[0] == landed[-1]  # newest first
    assert landed[0] not in shown  # the oldest fell off the tail
    # Off the list is not out of reach: naming one still resolves it.
    assert call(stores, "board", BERNA, milestone=landed[0])["milestone"]["id"] == landed[0]


def test_focusing_a_chapter_raises_the_done_cap(stores: Stores) -> None:
    """`DONE_SHOWN` bounds the BOARD's history, which grows forever. A chapter
    is a finite planned unit, and reviewing a finished one is exactly when
    somebody wants all of its cards — this project's own chapters closed 14 and
    22, and `20 of 22` cannot answer "what shipped"."""
    plan = call(
        stores,
        "plan",
        BERNA,
        milestone="wide",
        goal="g",
        tasks=[{"title": f"card {n}", "spec": "s"} for n in range(pulse.DONE_SHOWN + 2)],
    )
    for card in plan["cards"]:
        call(stores, "take", W1, task=card["id"])
        call(stores, "update", W1, task=card["id"], status="done", no_code=True, comment="done")
        call(stores, "merged", BERNA, task=card["id"], sha="9c2f")

    stone = plan["milestone"]["id"]
    assert len(call(stores, "board", BERNA, milestone=stone)["groups"]["done"]) == len(plan["cards"])
    # The board-wide read keeps the tight cap: there, `done` is history without end.
    call(stores, "merged", BERNA, milestone=stone, into="main", sha="9c2f")
    wide = call(stores, "board", BERNA)
    assert wide["milestone"] is None  # nothing open — no chapter narrows this read
    assert len(wide["groups"]["done"]) == pulse.DONE_SHOWN
    assert wide["done_total"] == len(plan["cards"])


# ── the dead worker ─────────────────────────────────────────────────────────


def test_a_dead_workers_card_comes_back_by_itself(
    stores: Stores, clock: Callable[[float], None]
) -> None:
    """THE point of deriving `doing` from the lease.

    Nobody calls anything. No sweep runs; no repair verb exists to run. The
    worker stops renewing and the card stops being `doing`, because being
    `doing` was never a row — it was the lease.
    """
    card = planned(stores)["cards"][0]["id"]
    call(stores, "assign", BERNA, tasks=[card])
    call(stores, "take", W1, task=card)
    assert [r["id"] for r in call(stores, "board", BERNA)["groups"]["doing"]] == [card]

    clock(LEASE_TTL + 60)  # the worker died. That is the whole of what happened.

    board = call(stores, "board", BERNA)
    assert board["groups"]["doing"] == []
    stalled = board["groups"]["stalled"]
    assert [r["id"] for r in stalled] == [card]
    assert stalled[0]["assignee"] == W1 and stalled[0]["quiet_for"] >= LEASE_TTL

    # and nothing was lost: the same worker walks straight back in
    assert call(stores, "take", W1, task=card)["state"] == "doing"


def test_a_stalled_card_is_handed_over_with_the_verb_that_already_existed(
    stores: Stores, clock: Callable[[float], None]
) -> None:
    card = planned(stores)["cards"][0]["id"]
    call(stores, "assign", BERNA, tasks=[card])
    call(stores, "take", W1, task=card)
    clock(LEASE_TTL + 60)

    with pytest.raises(Refused, match="assigned to agent:berna/w1"):
        call(stores, "take", W2, task=card)  # not yours to grab, even now

    call(stores, "assign", BERNA, tasks=[card], workers=["w2"])  # the orchestrator decides
    assert call(stores, "take", W2, task=card)["state"] == "doing"


def test_the_orchestrator_hands_over_a_card_whose_lease_is_still_live(
    stores: Stores, clock: Callable[[float], None]
) -> None:
    """The clock is not the authority on whether a worker is alive.

    A sub-agent that dies keeps renewing nothing, but its lease is live for up
    to `LEASE_TTL` — and for those minutes the orchestrator, which watched the
    process die, could not hand the card on. Waiting the clock out was waiting
    for a worse answer than the one it already had (`store/handover.py`).
    """
    card = planned(stores)["cards"][0]["id"]
    call(stores, "assign", BERNA, tasks=[card])
    call(stores, "take", W1, task=card)
    assert [r["id"] for r in call(stores, "board", BERNA)["groups"]["doing"]] == [card]

    clock(60)  # a minute later — the lease is unmistakably LIVE
    out = call(stores, "assign", BERNA, tasks=[card], workers=["w2"])

    assert out["briefs"][0]["displaced"] == W1  # said out loud, in the brief
    assert call(stores, "take", W2, task=card)["state"] == "doing"


def test_handing_a_card_to_the_worker_that_holds_it_leaves_its_lease_alone(
    stores: Stores, clock: Callable[[float], None]
) -> None:
    """Re-assigning to the same name is not a displacement, so it must not cost
    that worker the lease it is holding — nor report one."""
    card = planned(stores)["cards"][0]["id"]
    call(stores, "assign", BERNA, tasks=[card])
    lease = call(stores, "take", W1, task=card)
    clock(60)

    out = call(stores, "assign", BERNA, tasks=[card], workers=["w1"])

    assert out["briefs"][0]["displaced"] is None
    assert stores.live.holder(card, _clock.now()) == W1
    assert lease["state"] == "doing"


def test_a_live_worker_is_never_stalled(stores: Stores, clock: Callable[[float], None]) -> None:
    """The heartbeat is the traffic: any call renews the leases that actor holds."""
    card = planned(stores)["cards"][0]["id"]
    call(stores, "take", W1, task=card)
    clock(LEASE_TTL - 60)
    call(stores, "card", W1, task=card)  # any call renews
    clock(120)
    board = call(stores, "board", BERNA)
    assert board["groups"]["stalled"] == []
    assert [r["id"] for r in board["groups"]["doing"]] == [card]


# ── reading ─────────────────────────────────────────────────────────────────


def test_the_dossier_carries_the_whole_thread_and_the_collisions(stores: Stores) -> None:
    cards = planned(stores)["cards"]
    call(stores, "update", BERNA, task=cards[0]["id"], comment="careful: Decimal, not float")
    call(stores, "update", BERNA, task=cards[2]["id"], files=["src/models.py", "src/tax.py"])
    call(stores, "take", W1, task=cards[0]["id"])

    got = call(stores, "card", W1, task=cards[2]["id"])
    assert [c["id"] for c in got["collisions"]] == [cards[0]["id"]]
    assert got["collisions"][0]["holder"] == W1
    thread = call(stores, "card", W1, task=cards[0]["id"])["history"]
    assert [e["kind"] for e in thread] == ["created", "comment", "claimed"]


def test_search_looks_at_titles_and_specs(stores: Stores) -> None:
    planned(stores)
    hits = call(stores, "card", BERNA, query="bank export")["matches"]
    assert [h["matched"] for h in hits] == ["spec"]


def test_the_pulse_travels_with_every_answer(stores: Stores) -> None:
    planned(stores)
    for out in (call(stores, "board", BERNA), call(stores, "take", W1)):
        assert out["pulse"]["milestone"] == "MVP facturador"
        assert out["pulse"]["counts"]["ready"] >= 0


def test_report_counts_hours_from_the_events_themselves(
    stores: Stores, clock: Callable[[float], None]
) -> None:
    card = planned(stores)["cards"][0]["id"]
    call(stores, "take", W1, task=card)
    clock(600)
    call(stores, "update", W1, task=card, comment="halfway")
    out = call(stores, "report", BERNA, window="1d")
    assert out["by_actor"][W1]["seconds"] == 600.0
    assert out["by_actor"][W1]["human"] == "10m"


def test_report_carries_the_sessions_the_hours_are_made_of(
    stores: Stores, clock: Callable[[float], None]
) -> None:
    """The timesheet's blocks and the total beside them are ONE computation."""
    card = planned(stores)["cards"][0]["id"]
    call(stores, "take", W1, task=card)
    clock(600)
    call(stores, "update", W1, task=card, comment="halfway")
    out = call(stores, "report", BERNA, window="1d")
    blocks = out["by_actor"][W1]["sessions"]
    assert [(b["task"], b["seconds"]) for b in blocks] == [(card, 600.0)]
    assert blocks[0]["end"] - blocks[0]["start"] == 600.0
    assert out["by_actor"][W1]["sessions_total"] == len(blocks)
    assert sum(b["seconds"] for b in blocks) == out["by_actor"][W1]["seconds"]
    # The same fold per calendar day is what the timesheet reads, day by day.
    assert out["days"][-1]["by_actor"][W1]["sessions"] == blocks


# ── mentions ────────────────────────────────────────────────────────────────


def test_a_mention_reaches_the_actor_it_names_and_nobody_else(stores: Stores) -> None:
    card = planned(stores)["cards"][0]["id"]
    call(stores, "take", W1, task=card)
    call(stores, "update", W1, task=card, comment="Decimal or float?", mentions=[BERNA])

    board = call(stores, "board", BERNA)
    assert [m["id"] for m in board["groups"]["mentions"]] == [card]
    assert board["groups"]["mentions"][0]["by"] == W1
    assert board["groups"]["mentions"][0]["text"] == "Decimal or float?"
    assert board["pulse"]["mentions"] == 1

    # …and it is addressed to ONE reader: nobody else is asked to answer it.
    other = call(stores, "board", W2)
    assert other["groups"]["mentions"] == [] and other["pulse"]["mentions"] == 0


def test_a_mention_clears_itself_the_moment_the_actor_touches_the_card(
    stores: Stores, clock: Callable[[float], None]
) -> None:
    """The worked example, end to end. No verb clears it — there is none to call.

    This is `doing` and `blocked` again: the fact is derived from the thread, so
    answering IS the clearing, and nothing was written that could later be wrong.
    """
    card = planned(stores)["cards"][0]["id"]
    call(stores, "take", W1, task=card)
    call(stores, "update", W1, task=card, comment="Decimal or float?", mentions=[BERNA])
    clock(60)
    assert call(stores, "board", BERNA)["pulse"]["mentions"] == 1

    answer = call(stores, "update", BERNA, task=card, comment="Decimal, always")

    assert answer["pulse"]["mentions"] == 0  # gone in the very answer that cleared it
    board = call(stores, "board", BERNA)
    assert board["groups"]["mentions"] == [] and board["pulse"]["mentions"] == 0
    # and the mention itself is still in the thread — nothing was deleted
    said = [e for e in stores.events(card) if e["body"].get("mentions")]
    assert [e["body"]["mentions"] for e in said] == [[BERNA]]


def test_a_mention_on_a_closed_card_stops_asking(
    stores: Stores, clock: Callable[[float], None]
) -> None:
    card = planned(stores)["cards"][0]["id"]
    call(stores, "take", W1, task=card)
    call(stores, "update", W1, task=card, comment="worth a look before I close", mentions=[BERNA])
    clock(60)
    assert call(stores, "board", BERNA)["pulse"]["mentions"] == 1
    call(stores, "update", W1, task=card, status="done", no_code=True, comment="shipped")
    assert call(stores, "board", BERNA)["pulse"]["mentions"] == 0


def test_the_mention_count_rides_on_every_answer_not_only_the_board(
    stores: Stores, clock: Callable[[float], None]
) -> None:
    """The 'every turn' guarantee: whatever the reader calls next says ✉ 1.
    That is the job a Claude hook was asked to do, done by the pulse line."""
    cards = planned(stores)["cards"]
    call(stores, "update", BERNA, task=cards[0]["id"], comment="yours now", mentions=[W1])
    clock(60)
    for out in (
        call(stores, "take", W1, task=cards[1]["id"]),  # a different card entirely
        call(stores, "card", W1, task=cards[1]["id"]),
        call(stores, "update", W1, task=cards[1]["id"], comment="working"),
    ):
        assert out["pulse"]["mentions"] == 1


def test_a_mention_is_not_filtered_by_the_milestone_being_read(stores: Stores) -> None:
    """A mention addresses a PERSON. Scoped to the chapter on screen, the one
    thing it must never do — be missed — is what it would do."""
    card = planned(stores)["cards"][0]["id"]
    call(stores, "update", BERNA, task=card, comment="before you start", mentions=[W1])
    other = call(
        stores, "plan", BERNA, milestone="Reports", goal="monthly", tasks=[{"title": "the report"}]
    )
    board = call(stores, "board", W1, milestone=other["milestone"]["id"])
    assert [m["id"] for m in board["groups"]["mentions"]] == [card]


def test_anybody_may_write_on_a_card_somebody_else_holds(stores: Stores) -> None:
    """THE channel between agents in parallel. Reading and commenting are open
    to everyone; only taking, closing and releasing are the owner's.

    Refuse this and two agents whose work meets have nowhere to say so — they
    guess, or edit around each other, which is exactly the collision the
    worktrees make survivable and nothing else makes VISIBLE.
    """
    card = planned(stores)["cards"][0]["id"]
    call(stores, "assign", BERNA, tasks=[card])
    call(stores, "take", W1, task=card)  # w1 holds it and is alive on it

    out = call(stores, "update", W2, task=card, comment="I am in src/tax.py too", mentions=[W1])
    assert out["state"] == "doing"  # a comment never moved the card

    thread = [e for e in stores.events(card) if e["kind"] == "comment"]
    assert [e["actor"] for e in thread] == [W2]
    assert [m["by"] for m in call(stores, "board", W1)["groups"]["mentions"]] == [W2]
    # ...and w1 keeps the card: writing on it is not taking it.
    assert stores.live.holder(card, _clock.now()) == W1


def test_an_address_nobody_can_ever_match_is_refused_at_the_write(stores: Stores) -> None:
    """A typo'd actor would be a mention pending forever, addressed to nobody."""
    card = planned(stores)["cards"][0]["id"]
    with pytest.raises(BadRequest, match="not an identity"):
        call(stores, "update", BERNA, task=card, comment="oi", mentions=["w1"])
    assert [e["kind"] for e in stores.events(card)] == ["created"]  # nothing was written


def test_mentions_ride_on_a_comment_and_a_status_says_so(stores: Stores) -> None:
    """With status=, the comment IS the status event's note, so an address there
    would be silently dropped. Refused instead, naming the call that works."""
    card = planned(stores)["cards"][0]["id"]
    call(stores, "take", W1, task=card)
    with pytest.raises(BadRequest, match="rides on a comment"):
        call(
            stores,
            "update",
            W1,
            task=card,
            status="released",
            comment="over to you",
            mentions=[BERNA],
        )


def test_a_missing_card_says_how_to_look_for_it(stores: Stores) -> None:
    with pytest.raises(NotFound, match="taskops_card query"):
        call(stores, "card", BERNA, task="tk-000000")


# ── review (optional) ───────────────────────────────────────────────────────

R1 = "agent:berna/r1"
R2 = "agent:berna/r2"


def reviewed_plan(stores: Stores) -> dict[str, Any]:
    """Two cards in a chapter whose `reviews` default is on, plus one that opts out."""
    return call(
        stores,
        "plan",
        BERNA,
        milestone="MVP facturador",
        goal="read a bank CSV and issue invoices with VAT",
        reviews=True,
        tasks=[
            {"title": "invoice model", "spec": "the Invoice dataclass", "files": ["src/m.py"]},
            {"title": "CSV parser", "spec": "read the export", "files": ["src/p.py"]},
            {"title": "typo", "spec": "a comma", "files": ["src/c.py"], "review": False},
        ],
    )


def handed_in(stores: Stores, note: str = "model + tests, VAT rounds half up") -> str:
    """A card taken, committed and handed IN — the state a reviewer meets."""
    card = reviewed_plan(stores)["cards"][0]["id"]
    call(stores, "take", W1, task=card)
    call(stores, "bind", W1, task=card, sha="a1b2c3", subject="feat: model")
    call(stores, "update", W1, task=card, status="review", comment=note)
    return card


def test_a_chapter_can_default_to_review_and_a_card_can_opt_out(stores: Stores) -> None:
    cards = reviewed_plan(stores)["cards"]
    assert [c["review"] for c in cards] == [True, True, False]


def test_a_chapters_review_default_can_be_turned_on_and_off_afterwards(stores: Stores) -> None:
    """A DEFAULT, not a rule: it decides what a card is planned WITH, and never
    retro-flags one — the card carries its own `review`, and that is what the
    guards read."""
    stone = planned(stores)["milestone"]["id"]
    call(stores, "update", BERNA, milestone=stone, reviews=True)
    late = call(stores, "plan", BERNA, milestone=stone, tasks=[{"title": "audit"}])["cards"]
    assert late[0]["review"] is True
    assert call(stores, "card", BERNA, query="invoice model")["matches"][0]["state"] == "ready"
    call(stores, "update", BERNA, milestone=stone, reviews=False)
    later = call(stores, "plan", BERNA, milestone=stone, tasks=[{"title": "cleanup"}])["cards"]
    assert later[0]["review"] is False
    assert call(stores, "card", BERNA, task=late[0]["id"])["card"]["review"] is True


def test_a_card_that_needs_review_cannot_be_closed_by_its_worker(stores: Stores) -> None:
    """§6.1 — and the refusal names the way out, which is `status=review`."""
    card = handed_in(stores)
    with pytest.raises(Refused, match="status=review"):
        call(stores, "update", W1, task=card, status="done", comment="shipped")
    assert call(stores, "card", BERNA, task=card)["card"]["status"] == "open"
    # a card that does NOT require review is unaffected: its worker still closes it
    plain = call(stores, "card", BERNA, query="typo")["matches"][0]["id"]
    call(stores, "take", W2, task=plain)
    out = call(stores, "update", W2, task=plain, status="done", no_code=True, comment="a comma")
    assert out["card"]["status"] == "done"


def test_handing_in_is_refused_on_a_card_that_does_not_require_review(stores: Stores) -> None:
    plain = reviewed_plan(stores)["cards"][2]["id"]
    call(stores, "take", W1, task=plain)
    with pytest.raises(Refused, match="does not require review"):
        call(stores, "update", W1, task=plain, status="review", comment="have a look")


def test_you_may_not_pass_your_own_work(stores: Stores) -> None:
    """§6.2 — the one rule that gives review its value. Claim AND verdict."""
    card = handed_in(stores)
    with pytest.raises(Refused, match="somebody else reviews it"):
        call(stores, "review", W1, task=card)  # not even to read it under the lease
    with pytest.raises(Refused, match="somebody else reviews it"):
        call(stores, "review", W1, task=card, verdict="pass", note="looks great to me")


def test_a_verdict_needs_a_note_and_a_word_that_exists(stores: Stores) -> None:
    card = handed_in(stores)
    with pytest.raises(BadRequest, match="'pass'"):
        call(stores, "review", R1, task=card, verdict="lgtm", note="fine")
    with pytest.raises(Refused, match="verbatim"):
        call(stores, "review", R1, task=card, verdict="changes")


def test_reviewing_something_nobody_handed_in_says_who_hands_it_in(stores: Stores) -> None:
    card = reviewed_plan(stores)["cards"][0]["id"]
    with pytest.raises(Refused, match="has not been handed in"):
        call(stores, "review", R1, task=card)


def test_the_orchestrator_closes_what_a_reviewer_passed(stores: Stores) -> None:
    """§6.3 — and it closes it while the worker's lease is STILL LIVE, because
    the worker deliberately stays reachable after handing in."""
    card = handed_in(stores)
    assert call(stores, "board", BERNA)["groups"]["review"][0]["id"] == card
    call(stores, "review", R1, task=card)  # claims it
    out = call(stores, "review", R1, task=card, verdict="pass", note="checked the rounding")
    assert out["verdict"] == "pass"

    assert stores.live.holder(card, _clock.now()) == W1  # the worker never let go
    done = call(stores, "update", BERNA, task=card, status="done", comment="reviewed by r1")
    assert done["card"]["status"] == "done"
    assert [c["id"] for c in call(stores, "board", BERNA)["groups"]["merge"]] == [card]


def test_changes_requested_sends_it_back_with_the_note_verbatim(
    stores: Stores, clock: Callable[[float], None]
) -> None:
    """The reviewer's words reach the next take unshortened — a summary is
    where context goes to die."""
    note = "amounts are float in _total(); make them Decimal and round half up, 2 places"
    card = handed_in(stores)
    call(stores, "review", R1, task=card)
    call(stores, "review", R1, task=card, verdict="changes", note=note)

    clock(LEASE_TTL + 60)  # nobody is on it now — the board says whose move it is
    group = call(stores, "board", BERNA)["groups"]["changes"]
    assert [r["id"] for r in group] == [card]
    assert group[0]["text"] == note  # the reason, not just the id
    assert call(stores, "board", BERNA)["groups"]["stalled"] == []

    back = call(stores, "take", W1, task=card)
    assert back["standing"]["note"] == note and back["standing"]["verdict"] == "changes"
    assert back["standing"]["verdict_by"] == R1
    # and it is still not closable: the worker fixes it and hands it in again
    with pytest.raises(Refused, match="status=review"):
        call(stores, "update", W1, task=card, status="done", comment="fixed")
    call(stores, "update", W1, task=card, status="review", comment="Decimal everywhere")
    assert call(stores, "card", BERNA, task=card)["standing"]["verdict"] == ""


def test_a_dead_reviewer_frees_the_card_by_itself(
    stores: Stores, clock: Callable[[float], None]
) -> None:
    """§3.2 race 3, and the whole reason there is no `recover` for reviews.

    Nobody calls anything. The verifier stops renewing, its lease lapses, and
    the card leaves `reviewing` and returns to `review` on its own.
    """
    card = handed_in(stores)
    call(stores, "review", R1, task=card)
    board = call(stores, "board", BERNA)
    assert [r["id"] for r in board["groups"]["reviewing"]] == [card]
    assert board["groups"]["reviewing"][0]["holder"] == R1
    seq = stores.head()

    clock(LEASE_TTL + 60)  # the verifier died. That is the whole of what happened.

    board = call(stores, "board", BERNA)
    assert board["groups"]["reviewing"] == []
    assert [r["id"] for r in board["groups"]["review"]] == [card]
    assert stores.head() == seq  # no verb was called, and none exists to call
    assert call(stores, "review", R2, task=card)["card"]["id"] == card  # anybody may pick it up


def test_every_answer_that_names_a_state_knows_about_review(stores: Stores) -> None:
    """`derived()` takes the review facts everywhere it is called with the live
    ones. Without them, handing a card IN answers `doing` — the one call whose
    whole point was to stop working on it — and a search would never say so.
    """
    card = handed_in(stores)
    assert call(stores, "update", W1, task=card, comment="one more thing")["state"] == "review"
    assert call(stores, "card", BERNA, query="invoice model")["matches"][0]["state"] == "review"
    call(stores, "review", R1, task=card)
    assert call(stores, "card", BERNA, query="invoice model")["matches"][0]["state"] == "reviewing"


def test_a_reviewer_that_keeps_talking_never_loses_its_review(
    stores: Stores, clock: Callable[[float], None]
) -> None:
    """The traffic IS the heartbeat, for review leases exactly as for work ones:
    any call from the verifier renews it, so a long read never lapses under it."""
    card = handed_in(stores)
    call(stores, "review", R1, task=card)
    for _ in range(3):
        clock(LEASE_TTL * 0.6)
        call(stores, "board", R1)  # an ordinary read, nothing about reviewing
    assert [r["id"] for r in call(stores, "board", BERNA)["groups"]["reviewing"]] == [card]


def test_a_reviewing_row_carries_the_review_leases_own_acquired(
    stores: Stores, clock: Callable[[float], None]
) -> None:
    """`since` is the WORK lease's (or the card's `updated`) and `review_since`
    is the REVIEW lease's — two leases on one card, and a screen counting the
    second one down from the first can only state a floor that reads 0 while the
    review is provably still live (`ui/.../LiveLeases.tsx::checked`).

    The gap is the whole point: the card was handed in long before anybody
    started checking it, so the two timestamps are a TTL apart.
    """
    card = handed_in(stores)
    clock(LEASE_TTL + 60)  # the work lease lapses; the card waits, unchecked
    call(stores, "review", R1, task=card)
    row = call(stores, "board", BERNA)["groups"]["reviewing"][0]

    assert row["id"] == card and row["holder"] == R1
    assert row["review_since"] == _clock.now()  # the review began just now
    assert row["since"] <= _clock.now() - LEASE_TTL  # and the card is far older
    # the floor the UI falls back to would say 0 left; the real lease is full
    assert LEASE_TTL - (_clock.now() - row["since"]) <= 0
    assert LEASE_TTL - (_clock.now() - row["review_since"]) == LEASE_TTL


def test_two_reviewers_one_card_one_winner(stores: Stores) -> None:
    """§3.1 — the PK is the mutex, exactly like the work lease."""
    card = handed_in(stores)
    call(stores, "review", R1, task=card)
    with pytest.raises(Refused, match="already being reviewed by agent:berna/r1"):
        call(stores, "review", R2, task=card)
    call(stores, "review", R1, task=card)  # re-claiming your own review renews it
    # and the winner's verdict drops the lease, so the card leaves `reviewing`
    call(stores, "review", R1, task=card, verdict="changes", note="rounding")
    assert call(stores, "board", BERNA)["groups"]["reviewing"] == []


def test_a_board_that_never_sets_review_behaves_exactly_as_today(stores: Stores) -> None:
    """THE optionality test, end to end. Nothing about the old cycle changes."""
    card = planned(stores)["cards"][0]["id"]
    call(stores, "take", W1, task=card)
    with pytest.raises(Refused, match="does not require review"):
        call(stores, "update", W1, task=card, status="review", comment="have a look")
    with pytest.raises(Refused, match="does not require review"):
        call(stores, "review", R1, task=card)
    call(stores, "update", W1, task=card, status="done", no_code=True, comment="done")
    board = call(stores, "board", BERNA)
    assert board["groups"]["review"] == []
    assert board["groups"]["changes"] == []
    assert board["groups"]["reviewing"] == []
    assert [c["id"] for c in board["groups"]["merge"]] == [card]


def test_a_bound_commit_keeps_its_per_file_counts_and_a_binary_stays_null(
    stores: Stores,
) -> None:
    planned(stores)
    card = call(stores, "card", BERNA, query="invoice model")["matches"][0]["id"]
    call(stores, "take", W1, task=card)
    call(
        stores,
        "bind",
        W1,
        task=card,
        sha="a1b2c3",
        subject="feat: model",
        files=["src/models.py", "logo.png"],
        numstat={"src/models.py": [12, 3], "logo.png": None},
    )
    body = [e["body"] for e in stores.events(card) if e["kind"] == "commit"][0]
    assert body["files"] == ["src/models.py", "logo.png"]  # unchanged, byte for byte
    assert body["numstat"] == {"src/models.py": [12, 3], "logo.png": None}


def test_a_commit_bound_without_counts_carries_no_numstat_at_all(stores: Stores) -> None:
    """An old hook, or a commit queued before the key existed. Absent is
    absent: no key, and nothing invents zeros for it."""
    planned(stores)
    call(stores, "bind", W1, sha="deadbee", subject="chore: gitignore", files=[".gitignore"])
    body = [e["body"] for e in stores.events("project") if e["kind"] == "commit"][0]
    assert "numstat" not in body


def test_counts_that_are_not_a_pair_of_numbers_are_refused(stores: Stores) -> None:
    planned(stores)
    with pytest.raises(BadRequest, match="added, deleted"):
        call(
            stores,
            "bind",
            W1,
            sha="deadbee",
            subject="chore",
            files=["a.py"],
            numstat={"a.py": "3/1"},
        )


def test_a_commit_with_no_card_is_recorded_at_project_level(stores: Stores) -> None:
    """Nobody is forced to take a card to commit — the board just knows the sha
    happened. The `done` guard is untouched: it still demands a card-bound one.
    """
    planned(stores)
    out = call(stores, "bind", W1, sha="deadbee", subject="chore: gitignore", files=[".gitignore"])
    assert out["task"] == "project"
    assert [e["body"]["sha"] for e in stores.events("project") if e["kind"] == "commit"] == [
        "deadbee"
    ]

    card = call(stores, "card", BERNA, query="invoice model")["matches"][0]["id"]
    call(stores, "take", W1, task=card)
    with pytest.raises(Refused, match="no commit bound"):
        call(stores, "update", W1, task=card, status="done", comment="the sha is on project")


# ── the repo's web home (verbs/project.py) ──────────────────────────────────


def test_the_boards_repo_travels_in_the_board_payload(stores: Stores) -> None:
    """A project-level fact, so no card exists to carry it — and every client
    sees it through the same read, local or remote."""
    planned(stores)
    assert call(stores, "board", BERNA)["repo"] is None
    call(
        stores, "project", BERNA,
        op="remote", host="github.com", slug="bernatch22/taskops", url="https://github.com/bernatch22/taskops",
    )
    assert call(stores, "board", BERNA)["repo"] == {
        "host": "github.com",
        "slug": "bernatch22/taskops",
        "url": "https://github.com/bernatch22/taskops",
    }


def test_recording_the_same_origin_twice_writes_nothing(
    stores: Stores, clock: Callable[[float], None]
) -> None:
    """`init` is re-run all the time; the log is replayed forever and has no
    delete, so an unchanged fact must not append."""
    args = {"op": "remote", "host": "github.com", "slug": "a/b", "url": "https://github.com/a/b"}
    first = call(stores, "project", BERNA, **args)
    clock(60)
    second = call(stores, "project", BERNA, **args)
    assert first["recorded"] and not second["recorded"]
    assert len([e for e in stores.events("project") if e["kind"] == "project"]) == 1


def test_a_changed_origin_wins_by_being_later(
    stores: Stores, clock: Callable[[float], None]
) -> None:
    call(stores, "project", BERNA, op="remote", host="github.com", slug="a/b")
    clock(60)
    call(stores, "project", BERNA, op="remote", host="gitlab.com", slug="team/sub/c")
    repo = call(stores, "board", BERNA)["repo"]
    assert repo == {"host": "gitlab.com", "slug": "team/sub/c", "url": "https://gitlab.com/team/sub/c"}


def test_an_unknown_project_fact_is_refused_by_name(stores: Stores) -> None:
    with pytest.raises(BadRequest, match="not a project fact"):
        call(stores, "project", BERNA, op="mascot", slug="a/b")


# ── the forge that opens the board (op=forge) ───────────────────────────────


def test_a_board_declares_no_forge_and_that_is_how_every_board_is_born(
    stores: Stores,
) -> None:
    """The chapter's opt-in rule, at its only reader. Absent is not a special
    case to remember — it is the answer `forge()` gives before anyone speaks,
    and the board payload gains no key for it, so nothing downstream can even
    see that the op exists."""
    planned(stores)
    assert project.forge(stores) is None
    assert "forge" not in call(stores, "board", BERNA)


def test_the_board_payload_says_what_opens_it(stores: Stores) -> None:
    """The fact stops being the owner's private knowledge.

    `visibility`'s precedent, exactly (`verbs/pulse.py`): derived per read from
    the one place it was declared, never a second copy. Before this key the only
    two parties who could tell that `--github` works here were the owner who
    declared the forge and the stranger the door refused — an agent with full
    board access could not, and neither could the dashboard.

    The payload carries the WHOLE fact and nothing reshaped: the door reads
    `{host, repo, need}` and so does a reader, so a screen can name the repo AND
    the access without knowing the default.
    """
    call(stores, "project", BERNA, op="forge", repo="cloudacio/Axion", need="admin")
    assert call(stores, "board", BERNA)["forge"] == {
        "host": "github.com",
        "repo": "cloudacio/Axion",
        "need": "admin",
    }


def test_a_cleared_forge_takes_the_key_out_of_the_payload_again(
    stores: Stores, clock: Callable[[float], None]
) -> None:
    """Absent stays ABSENT — the key is never sent as `null`.

    A cleared forge is the same board as one that never declared one (the door's
    own rule, `core/forge.py::understood`), so the payload has to be the same
    payload: a reader that learned "the key is there, look at its value" would
    read `null` as a forge whose fields are missing. There is one shape for "no
    GitHub door here", and it is no key.
    """
    call(stores, "project", BERNA, op="forge", repo="cloudacio/Axion")
    clean = set(call(stores, "board", BERNA)) - {"forge"}
    clock(60)
    call(stores, "project", BERNA, op="forge", repo="")
    after = call(stores, "board", BERNA)
    assert "forge" not in after and set(after) == clean


def test_the_declared_forge_is_what_the_door_will_read(stores: Stores) -> None:
    """The vocabulary, whole: `{host, repo, need}`, with github.com and `push`
    as the defaults a caller may leave out — and the SAME dict from the write
    and from the read, because the door reads it back, never the answer."""
    out = call(stores, "project", BERNA, op="forge", repo="bernatch22/taskops")
    assert out["value"] == {"host": "github.com", "repo": "bernatch22/taskops", "need": "push"}
    assert out["recorded"] and project.forge(stores) == out["value"]

    asked = call(stores, "project", BERNA, op="forge", repo="cloudacio/Axion", need="admin")
    assert asked["value"] == {"host": "github.com", "repo": "cloudacio/Axion", "need": "admin"}
    assert project.forge(stores) == asked["value"]


def test_declaring_a_forge_is_reversible(stores: Stores, clock: Callable[[float], None]) -> None:
    """`repo=""` is the way BACK to invite-only. Opting in has to be undoable
    in the same breath it was done, or a mistyped owner is permanent."""
    call(stores, "project", BERNA, op="forge", repo="bernatch22/taskops")
    clock(60)
    assert call(stores, "project", BERNA, op="forge", repo="")["value"] is None
    assert project.forge(stores) is None


def test_a_repo_that_is_not_owner_name_is_refused_rather_than_trimmed(stores: Stores) -> None:
    """`GET /repos/{owner}/{name}` has nowhere to put a third segment, so a
    GitLab-shaped slug is a refusal and never a truncation; the value the
    caller has in hand is `remote.parse`'s `slug`, which is exactly this."""
    for wrong in ("taskops", "team/sub/repo", "bernatch22/", "/taskops", "bern atch/taskops"):
        with pytest.raises(BadRequest, match="exactly owner/name"):
            call(stores, "project", BERNA, op="forge", repo=wrong)
    assert project.forge(stores) is None


def test_a_forge_this_host_cannot_ask_is_refused_at_declaration(stores: Stores) -> None:
    """A board must never carry a promise nothing can keep: the host that can
    be ASKED about membership is a shorter list than the hosts `remote` stores,
    and the refusal says the repo is still recordable as the board's remote."""
    with pytest.raises(BadRequest, match="does not open it"):
        call(stores, "project", BERNA, op="forge", host="gitlab.com", repo="team/thing")


def test_read_access_is_not_a_membership(stores: Stores) -> None:
    """`need=pull` would open a public repo's board to everyone with a browser.
    It is not in the pair, so it is refused by name rather than defaulted."""
    with pytest.raises(BadRequest, match="Read access is not a membership"):
        call(stores, "project", BERNA, op="forge", repo="bernatch22/taskops", need="pull")


def test_a_forge_nobody_can_verify_reads_as_no_forge(stores: Stores) -> None:
    """The read side refuses SILENTLY, and that asymmetry is the point: a
    declaration can reach `state()` from a log another version wrote or a hand
    edit, and a door that GRANTS on this answer must see "no forge" rather than
    a half-understood promise. Written straight to the log, past the verb."""
    from taskops.core.event import make

    junk: list[Any] = [
        {"host": "gitlab.com", "repo": "a/b", "need": "push"},  # a host nobody can ask
        {"host": "github.com", "repo": "team/sub/repo", "need": "push"},  # no such API path
        {"host": "github.com", "repo": "a/b", "need": "pull"},  # not a membership
        {"repo": "a/b"},  # half a declaration
        "github",  # not even an object
    ]
    for value in junk:
        stores.write([make("project", BERNA, "project", {"op": "forge", "value": value}, 1000.0)])
        assert project.forge(stores) is None


# ── the log itself: the events verb and its keyset paging ───────────────────


def _noisy(stores: Stores) -> list[str]:
    """A board whose log is worth paging, and the truth to compare against.

    Every event lands at the SAME instant — the `clock` fixture is frozen — so
    this is exactly the case a `ts` cursor cannot survive. Ground truth comes
    from `events.jsonl` itself, in file order, never from the cache the verb
    reads: comparing a query with itself proves nothing.
    """
    planned(stores)
    card = call(stores, "board", BERNA)["groups"]["take"][0]["id"]
    for i in range(12):
        call(stores, "update", BERNA, task=card, comment=f"c{i}")
    call(stores, "project", BERNA, op="remote", host="github.com", slug="a/b")
    written, _ = log.read(stores.log_path)
    return [e["id"] for e in reversed(written)]  # newest first, as the pane reads


def test_the_events_verb_answers_with_the_log_newest_first_and_its_real_total(
    stores: Stores,
) -> None:
    newest_first = _noisy(stores)
    page = call(stores, "events", BERNA, limit=5)
    assert [e["id"] for e in page["events"]] == newest_first[:5]
    # The counter is the LOG's length, not this page's.
    assert page["total"] == len(newest_first) > 5
    assert page["head"] == stores.head()


def test_paging_the_log_crosses_a_boundary_without_dropping_or_repeating_a_row(
    stores: Stores,
) -> None:
    """THE test this verb exists to pass. Every event shares one `ts`, so a
    cursor on the timestamp would either skip the rows tying at the boundary or
    serve them twice; the cursor is the rowid and neither can happen."""
    newest_first = _noisy(stores)
    seen: list[str] = []
    cursor: int | None = None
    pages = 0
    while True:
        args: dict[str, Any] = {"limit": 4}
        if cursor is not None:
            args["before"] = cursor
        page = call(stores, "events", BERNA, **args)
        seen += [e["id"] for e in page["events"]]
        pages += 1
        cursor = page["next"]
        if cursor is None:
            break
    assert pages > 3, "the fixture must actually cross several boundaries"
    assert seen == newest_first  # order kept, nothing dropped
    assert len(set(seen)) == len(seen)  # nothing served twice


def test_the_stream_carries_board_history_and_not_only_cards(stores: Stores) -> None:
    """`task="project"` rows — a repo bound, a chapter opened — are the board's
    own history and belong in the stream. A card-shaped filter would hide them."""
    _noisy(stores)
    everything = call(stores, "events", BERNA, limit=200)["events"]
    assert any(e["task"] == "project" for e in everything)


def test_a_page_is_refused_a_size_it_cannot_serve(stores: Stores) -> None:
    _noisy(stores)
    with pytest.raises(BadRequest, match="outside 1..200"):
        call(stores, "events", BERNA, limit=5000)


# ── the wave: what is safe to dispatch together (core/seams.py) ──────────────


PROSE = """The board refuses a close that has no commit behind it, and the
refusal names the call that works. Nothing here is stored; it is derived on
every read, which is the whole point — a row survives the process that wrote
it and a lease does not. Read the module before changing its decision."""


def test_ordinary_prose_bears_no_concept_at_all() -> None:
    """The narrowness IS the feature: one false hold and the orchestrator stops
    reading the wave, which costs more than every seam it would ever catch."""
    assert seams.terms(PROSE) == frozenset()


def test_the_three_documented_shapes_are_what_a_concept_looks_like() -> None:
    got = seams.terms(
        "Both cards check `git remote get-url origin`, then draw "
        "`panels.ts::WorktreeRow` from what `live.renew` decided."
    )
    assert "git remote get-url origin" in got
    assert "panels.ts::worktreerow" in got
    assert "live.renew" in got


def test_a_bare_backticked_word_is_not_a_concept() -> None:
    """Half the specs on this board backtick `done`, `main` and `open`."""
    assert seams.terms("it closes `done` on `main`, never while `open`") == frozenset()


def test_a_hyphen_is_not_a_joiner() -> None:
    """`post-mortem` and `read-only` are prose; `done_total` is an identifier."""
    assert seams.terms("the read-only post-mortem") == frozenset()
    assert seams.terms("the read-only done_total") == frozenset({"done_total"})


def test_overlaps_reports_only_the_pairs_that_share_something() -> None:
    found = seams.overlaps(
        {
            "tk-a": "read `store/cache.py` and page it",
            "tk-b": "write `store/cache.py` faster",
            "tk-c": "nothing in common here at all",
        }
    )
    assert found == [("tk-a", "tk-b", frozenset({"store/cache.py"}))]


def waved(stores: Stores, **kwargs: Any) -> Any:
    return call(stores, "board", BERNA, **kwargs)["wave"]


def test_disjoint_ready_cards_are_all_safe_to_dispatch_together(stores: Stores) -> None:
    planned(stores)
    wave = waved(stores)
    assert [c["title"] for c in call(stores, "board", BERNA)["groups"]["take"]] == [
        "invoice model",
        "CSV parser",
    ]
    assert len(wave["safe"]) == 2 and wave["held"] == []


def test_a_shared_file_holds_a_card_and_names_the_file(stores: Stores) -> None:
    out = call(
        stores,
        "plan",
        BERNA,
        milestone="two halves",
        goal="one file, two cards",
        tasks=[
            {"title": "left", "spec": "the left half", "files": ["src/tax.py"]},
            {"title": "right", "spec": "the right half", "files": ["src/tax.py", "src/x.py"]},
        ],
    )
    first, second = (c["id"] for c in out["cards"])
    wave = waved(stores, milestone=out["milestone"]["id"])
    assert wave["safe"] == [first]
    assert wave["held"] == [
        {"id": second, "title": "right", "why": {"with": first, "files": ["src/tax.py"]}}
    ]


def test_a_shared_concept_holds_a_card_even_with_disjoint_files(stores: Stores) -> None:
    """The two `gitwork/remote.py` cards, reproduced: different declared files,
    the same sentence in both specs."""
    out = call(
        stores,
        "plan",
        BERNA,
        milestone="the forge",
        goal="link out to github",
        tasks=[
            {"title": "links", "spec": "check `git remote get-url origin`", "files": ["a.py"]},
            {"title": "pushes", "spec": "we check `git remote get-url origin`", "files": ["b.py"]},
        ],
    )
    first, second = (c["id"] for c in out["cards"])
    wave = waved(stores, milestone=out["milestone"]["id"])
    assert wave["safe"] == [first]
    assert wave["held"][0]["why"] == {"with": first, "terms": ["git remote get-url origin"]}


def test_when_both_hold_the_reader_gets_the_declared_fact(stores: Stores) -> None:
    """THE LIVE CASE, from this repo's own board on 2026-08-09: the orchestrator
    held tk-dfaff7 apart from tk-814c7b by hand because both declare
    `src/taskops/mcp/gitmoves.py` and `tests/test_mcp.py` — and both specs also
    name `taskops_merge`. Files and terms both fire; the answer is the FILES,
    because a declared file is a fact the planner wrote and a term is an
    inference from prose."""
    out = call(
        stores,
        "plan",
        BERNA,
        milestone="landing",
        goal="one call integrates the chapter, and a chapter lands over a moved trunk",
        tasks=[
            {
                "title": "batch",
                "spec": "one taskops_merge call integrates every done card",
                "files": ["src/taskops/mcp/gitmoves.py", "tests/test_mcp.py"],
            },
            {
                "title": "landing gate",
                "spec": "taskops_merge milestone= catches the trunk up first",
                "files": ["src/taskops/mcp/gitmoves.py", "tests/test_mcp.py"],
            },
        ],
    )
    first, second = (c["id"] for c in out["cards"])
    wave = waved(stores, milestone=out["milestone"]["id"])
    assert wave["safe"] == [first]
    assert wave["held"][0]["why"] == {
        "with": first,
        "files": ["src/taskops/mcp/gitmoves.py", "tests/test_mcp.py"],
    }
    both = {"tk-a": out["cards"][0]["spec"], "tk-b": out["cards"][1]["spec"]}
    assert seams.overlaps(both) == [("tk-a", "tk-b", frozenset({"taskops_merge"}))]


def test_one_ready_card_has_no_wave_to_compute(stores: Stores) -> None:
    out = call(
        stores,
        "plan",
        BERNA,
        milestone="alone",
        goal="one card",
        tasks=[{"title": "only", "spec": "by itself", "files": ["x.py"]}],
    )
    assert waved(stores, milestone=out["milestone"]["id"]) is None


# ── reports: the file is in git, the board holds the pointer (verbs/filed.py) ─


REPORT = ".taskops/reports/mvp-facturador.md"


def test_a_filed_report_is_a_pointer_on_the_chapter_and_rides_on_the_board_read(
    stores: Stores,
) -> None:
    """The seam, end to end: one write, and both consumers can see it — the row
    carries what a list needs (title, when, who) and what a renderer needs (the
    path and the sha to read it at)."""
    planned(stores)
    out = call(stores, "filed", W1, path=REPORT, title="MVP facturador", sha="a1b2c3d")
    assert out["recorded"] is True
    stone = call(stores, "board", BERNA)["milestone"]["id"]
    assert out["report"]["milestone"] == stone  # the single open chapter, unasked
    assert out["report"]["by"] == W1

    board = call(stores, "board", BERNA)
    assert board["reports_total"] == 1
    assert [r["path"] for r in board["reports"]] == [REPORT]
    row = board["reports"][0]
    assert row["title"] == "MVP facturador" and row["sha"] == "a1b2c3d"
    assert row["by"] == W1 and row["ts"] == _clock.now() and row["id"]


def test_the_log_grows_by_a_pointer_and_never_by_the_report(stores: Stores) -> None:
    """The chapter's rule, measured where it can be measured: the API has no
    door for the prose at all, so whatever the file weighs, the log gains four
    short strings. A body key for content would fail this the moment it existed.
    """
    planned(stores)
    before = stores.log_path.stat().st_size
    call(stores, "filed", W1, path=REPORT, title="MVP facturador" * 4, sha="a1b2c3d")
    assert stores.log_path.stat().st_size - before < 1024
    body = [e["body"] for e in stores.events("project") if e["kind"] == "report"][0]
    assert set(body) == {"path", "title", "milestone", "sha"}


def test_a_report_outside_the_reports_directory_is_refused_and_the_way_in_is_named(
    stores: Stores,
) -> None:
    planned(stores)
    with pytest.raises(Refused, match=r"\.taskops/reports/") as refused:
        call(stores, "filed", W1, path="notes/whatever.md", title="t", sha="a1b2c3d")
    assert "filed path=" in str(refused.value)  # the refusal contains the call that works
    with pytest.raises(Refused):
        call(stores, "filed", W1, path=".taskops/reports/../../etc/passwd", title="t", sha="a")
    assert [e for e in stores.events("project") if e["kind"] == "report"] == []


def test_a_report_needs_a_title_and_the_sha_that_carries_it(stores: Stores) -> None:
    """A row with no title cannot be read in a list; a path with no sha cannot
    be fetched. Both are the whole point of the event."""
    planned(stores)
    with pytest.raises(BadRequest, match="title="):
        call(stores, "filed", W1, path=REPORT, title="  ", sha="a1b2c3d")
    with pytest.raises(BadRequest, match="sha="):
        call(stores, "filed", W1, path=REPORT, title="t", sha="")


def test_filing_the_same_report_twice_writes_nothing(
    stores: Stores, clock: Callable[[float], None]
) -> None:
    """A retry after a dropped connection must not leave two rows in a list a
    screen draws — `verbs/project.py`'s rule, and the log has no delete."""
    planned(stores)
    first = call(stores, "filed", W1, path=REPORT, title="MVP", sha="a1b2c3d")
    clock(60)
    again = call(stores, "filed", W1, path=REPORT, title="MVP", sha="a1b2c3d")
    assert first["recorded"] and not again["recorded"]
    assert again["report"]["ts"] == first["report"]["ts"]  # the ORIGINAL, not a new one
    assert call(stores, "board", BERNA)["reports_total"] == 1


def test_the_same_path_at_a_new_sha_is_a_new_report(
    stores: Stores, clock: Callable[[float], None]
) -> None:
    """The file was rewritten, and both versions stay in the history with the
    commit each one lived at — that is what makes the pointer worth storing."""
    planned(stores)
    call(stores, "filed", W1, path=REPORT, title="MVP", sha="a1b2c3d")
    clock(60)
    call(stores, "filed", W1, path=REPORT, title="MVP, rewritten", sha="ffffff1")
    board = call(stores, "board", BERNA)
    assert board["reports_total"] == 2
    assert [r["sha"] for r in board["reports"]] == ["ffffff1", "a1b2c3d"]  # newest first


def test_both_roles_may_file_a_report(stores: Stores) -> None:
    """A chapter is not a card: nobody holds it, so there is no owner to be the
    only one allowed to narrate it. The orchestrator and a worker file alike."""
    planned(stores)
    call(stores, "filed", BERNA, path=".taskops/reports/one.md", title="by the dev", sha="a1")
    call(stores, "filed", W1, path=".taskops/reports/two.md", title="by the worker", sha="b2")
    assert {r["by"] for r in call(stores, "board", BERNA)["reports"]} == {BERNA, W1}


def test_the_reports_list_is_capped_and_says_how_many_there_really_are(
    stores: Stores,
) -> None:
    """`done_total`'s idiom, which this chapter's rules make a requirement: a
    truncated list that does not say so is a screen quietly losing history."""
    planned(stores)
    for i in range(_facts.REPORTS_SHOWN + 2):
        call(stores, "filed", W1, path=f".taskops/reports/{i}.md", title=f"r{i}", sha=f"sha{i}")
    board = call(stores, "board", BERNA)
    assert board["reports_total"] == _facts.REPORTS_SHOWN + 2
    assert len(board["reports"]) == _facts.REPORTS_SHOWN


def test_reports_are_scoped_to_the_chapter_in_focus(stores: Stores) -> None:
    """Two chapters, two narrations, and neither leaks into the other's read."""
    first = planned(stores)["milestone"]["id"]
    second = call(
        stores, "plan", BERNA, milestone="Reports", goal="narrate", tasks=[{"title": "x"}]
    )["milestone"]["id"]
    call(stores, "filed", W1, milestone=first, path=".taskops/reports/one.md", title="A", sha="a1")
    call(stores, "filed", W1, milestone=second, path=".taskops/reports/two.md", title="B", sha="b2")
    assert [r["title"] for r in call(stores, "board", BERNA, milestone=first)["reports"]] == ["A"]
    assert [r["title"] for r in call(stores, "board", BERNA, milestone=second)["reports"]] == ["B"]
    # Nothing in focus is the whole board, the way `events` is board-wide.
    assert call(stores, "board", BERNA)["reports_total"] == 2


def test_a_report_on_no_chapter_and_on_a_chapter_that_does_not_exist(stores: Stores) -> None:
    """With several open chapters the board asks instead of guessing — the same
    bargain `taskops_plan` makes, refusal included."""
    planned(stores)
    call(stores, "plan", BERNA, milestone="Reports", goal="narrate", tasks=[{"title": "x"}])
    with pytest.raises(BadRequest, match="no single open milestone"):
        call(stores, "filed", W1, path=REPORT, title="t", sha="a1")
    with pytest.raises(NotFound, match="does not exist"):
        call(stores, "filed", W1, milestone="ms-000000", path=REPORT, title="t", sha="a1")


def test_a_report_moves_no_card_and_no_state(stores: Stores) -> None:
    """History-only: filing one changes nothing about the work itself, and the
    board it is filed on looks exactly as it did."""
    planned(stores)
    before = call(stores, "board", BERNA)["groups"]
    call(stores, "filed", W1, path=REPORT, title="MVP", sha="a1b2c3d")
    after = call(stores, "board", BERNA)["groups"]
    assert before == after
    assert all(c["status"] == "open" for c in stores.state()["cards"].values())


# ── activity: N cards' whole story in ONE read (verbs/activity.py) ───────────


def carried(stores: Stores) -> tuple[str, str]:
    """A chapter whose first card was carried all the way — taken, released,
    re-taken, committed, closed and integrated — so a story has something to
    say in every field it declares."""
    plan = planned(stores)
    card = plan["cards"][0]["id"]
    call(stores, "take", W1, task=card)
    call(
        stores,
        "update",
        W1,
        task=card,
        status="released",
        comment="got as far as the VAT rounding",
    )
    call(stores, "take", W2, task=card)
    call(
        stores,
        "bind",
        W2,
        task=card,
        sha="a1b2c3",
        subject="feat: the Invoice model",
        files=["src/models.py"],
        numstat={"src/models.py": [12, 3]},
    )
    call(stores, "update", W2, task=card, status="done", comment="model + tests")
    call(stores, "merged", BERNA, task=card, sha="9c2f")
    return plan["milestone"]["id"], card


def test_activity_answers_a_whole_chapter_in_one_read(stores: Stores) -> None:
    """What N `card` calls answered, once — and the chapter's header sent ONCE
    instead of re-sent with every one of them."""
    stone, card = carried(stores)
    out = call(stores, "activity", BERNA, milestone=stone)

    assert out["milestone"]["goal"] == "read a bank CSV and issue invoices with VAT"
    assert out["cards_total"] == 5 and len(out["cards"]) == 5
    story = next(c for c in out["cards"] if c["id"] == card)
    assert story["state"] == "done"
    assert story["branch"] == card and story["merged_into"] == "ms/mvp-facturador"
    assert story["commits"] == [
        {
            "sha": "a1b2c3",
            "subject": "feat: the Invoice model",
            "files": ["src/models.py"],
            "branch": "",
            "numstat": {"src/models.py": [12, 3]},
        }
    ]
    # The previous worker's note, verbatim — the same field a take is shown.
    assert story["resume"] == "got as far as the VAT rounding"
    assert story["seconds"] >= 0 and story["thread_total"] == len(stores.events(card))


def test_activity_carries_pointers_into_git_and_never_a_diff(stores: Stores) -> None:
    """The chapter's rule: branch, shas and merged_into are what a reader
    follows into its own clone. Nothing here is patch text, and a commit body
    is a MEASURE (numstat) rather than the lines it counts."""
    stone, _ = carried(stores)
    out = call(stores, "activity", BERNA, milestone=stone, depth="full")
    for story in out["cards"]:
        for commit in story["commits"]:
            assert set(commit) <= {"sha", "subject", "files", "numstat", "branch"}
    assert "@@" not in json.dumps(out)  # a hunk header — the shape of a patch


def test_activity_caps_the_thread_and_says_how_long_it_really_is(stores: Stores) -> None:
    """The done/done_total idiom, which this chapter's rules make a requirement:
    the headline sends `THREAD_HEADLINE` events and the honest total beside
    them, so "0 of 8" is actionable where a paragraph that stops is not."""
    stone, card = carried(stores)
    real = len(stores.events(card))
    assert real > _stories.THREAD_HEADLINE  # there IS something being capped

    head = next(c for c in call(stores, "activity", BERNA, milestone=stone)["cards"] if c["id"] == card)
    assert len(head["thread"]) == _stories.THREAD_HEADLINE
    assert len(head["thread"]) < head["thread_total"] == real  # capped, and it SAYS so
    assert "spec" not in head and "criteria" not in head and "files" not in head

    whole = next(
        c
        for c in call(stores, "activity", BERNA, milestone=stone, depth="full")["cards"]
        if c["id"] == card
    )
    assert len(whole["thread"]) == whole["thread_total"] == real
    assert whole["spec"] == "the Invoice dataclass" and whole["files"] == ["src/models.py"]


#: The fixture below is this board's OWN measured shape (2026-08-10), each
#: number rounded UP: 1.6 commits per card → 2, 4.7 files per commit → 6, and 6
#: events per card → 10, of which 4 are long comments rather than statuses. A
#: budget pinned against a fixture invented out of nothing pins nothing.
COMMITS, FILES, COMMENTS = 2, 6, 4


def test_seventy_six_cards_at_headline_fit_the_payload_budget(stores: Stores) -> None:
    """The card's acceptance, MEASURED rather than assumed: 76 cards, each with
    a 2KB spec, its commits with their numstat, and a thread of long comments.
    At `full` the same read is several times bigger — which is exactly why
    `headline` is the default and why the two long fields are the two it drops."""
    call(
        stores,
        "plan",
        BERNA,
        milestone="A chapter that grew",
        goal="g",
        tasks=[
            {"title": f"card {i}", "spec": "why this exists. " * 120, "files": ["src/a.py"]}
            for i in range(76)
        ],
    )
    for n, card in enumerate(stores.state()["cards"].values()):
        for commit in range(COMMITS):
            call(
                stores,
                "bind",
                W1,
                task=card["id"],
                sha=f"{n:04x}{commit}",
                subject="feat: something with a subject of an ordinary length",
                files=[f"src/module_{f}.py" for f in range(FILES)],
                numstat={f"src/module_{f}.py": [f * 3, f] for f in range(FILES)},
            )
        for comment in range(COMMENTS):
            call(stores, "update", W1, task=card["id"], comment=f"{comment}: what I found. " * 40)

    out = call(stores, "activity", BERNA, milestone="", depth="headline")
    size = len(json.dumps(out))
    assert len(out["cards"]) == 76
    assert size < 100 * 1024, f"{size} bytes for 76 cards at headline"
    assert len(json.dumps(call(stores, "activity", BERNA, depth="full"))) > 4 * size


def test_activity_since_returns_only_what_moved_and_still_counts_the_rest(
    stores: Stores,
) -> None:
    """`since=` is the cache's keyset (`store/cache.py::page`'s cursor), not a
    second one — and an empty answer under it means "nothing moved", which is
    why `cards_total` keeps counting the chapter."""
    stone, card = carried(stores)
    seq = call(stores, "activity", BERNA, milestone=stone)["seq"]

    quiet = call(stores, "activity", BERNA, milestone=stone, since=seq)
    assert quiet["cards"] == [] and quiet["cards_total"] == 5

    other = call(stores, "card", BERNA, query="CSV parser")["matches"][0]["id"]
    call(stores, "update", BERNA, task=other, comment="the bank changed its export")
    moved = call(stores, "activity", BERNA, milestone=stone, since=seq)
    assert [c["id"] for c in moved["cards"]] == [other]
    assert moved["cards_total"] == 5 and moved["seq"] > seq
    assert card not in {c["id"] for c in moved["cards"]}


def test_activity_reads_named_cards_across_chapters(stores: Stores) -> None:
    """`tasks=` is the narrower question and wins. The header is the chapter
    they SHARE — nothing at all when they do not, rather than one of the two
    chosen silently."""
    first = planned(stores)["cards"][0]["id"]
    second = call(
        stores, "plan", BERNA, milestone="Reports", goal="narrate", tasks=[{"title": "x"}]
    )["cards"][0]["id"]
    both = call(stores, "activity", BERNA, tasks=[first, second])
    assert [c["id"] for c in both["cards"]] == [first, second]
    assert both["milestone"] is None
    one = call(stores, "activity", BERNA, tasks=[second])
    assert one["milestone"] is not None and one["milestone"]["title"] == "Reports"


def test_activity_carries_the_chapters_reports(stores: Stores) -> None:
    """The seam card's fold, consumed: a chapter's narrations ride on the read
    that tells its story, capped with the honest total (`_facts.reports`)."""
    stone, _ = carried(stores)
    call(stores, "filed", W1, path=REPORT, title="MVP facturador", sha="a1b2c3d")
    out = call(stores, "activity", BERNA, milestone=stone)
    assert [r["title"] for r in out["reports"]] == ["MVP facturador"]
    assert out["reports_total"] == 1


def test_activity_is_a_read_anonymous_may_run_and_it_writes_nothing(stores: Stores) -> None:
    """WATCHERS, and the milestone's rule: no lease renewed for anon, nothing
    written anywhere. A `presence` row on a public read is the invisible
    anonymous write ARCHITECTURE §11 bans."""
    stone, _ = carried(stores)
    head, present = stores.head(), stores.live.present(0.0)
    out = call(stores, "activity", ANON, milestone=stone)
    assert out["cards_total"] == 5
    assert stores.head() == head
    assert stores.live.present(0.0) == present


def test_activity_refuses_what_it_cannot_answer_and_names_the_door(stores: Stores) -> None:
    planned(stores)
    call(stores, "plan", BERNA, milestone="Reports", goal="narrate", tasks=[{"title": "x"}])
    with pytest.raises(BadRequest, match="milestone=ms-…"):
        call(stores, "activity", BERNA)  # two open chapters: asked, never guessed
    with pytest.raises(NotFound, match="does not exist"):
        call(stores, "activity", BERNA, milestone="ms-000000")
    with pytest.raises(BadRequest, match="headline or full"):
        call(stores, "activity", BERNA, milestone="", depth="everything")


def test_the_commits_list_is_capped_and_says_how_many_there_really_are(stores: Stores) -> None:
    """The other half of the same rule: every capped list travels with its
    honest total. `commits` is the one field a single card can grow without a
    bound anybody controls, so it is capped NEWEST-first — the recent work is
    what a chapter-wide reader is deciding about."""
    plan = planned(stores)
    card = plan["cards"][0]["id"]
    extra = 3
    for i in range(_stories.COMMITS_SHOWN + extra):
        call(stores, "bind", W1, task=card, sha=f"{i:06x}", subject=f"c{i}", files=["src/a.py"])
    out = call(stores, "activity", BERNA, milestone=plan["milestone"]["id"])
    story = next(c for c in out["cards"] if c["id"] == card)
    assert story["commits_total"] == _stories.COMMITS_SHOWN + extra
    assert len(story["commits"]) == _stories.COMMITS_SHOWN
    assert story["commits"][-1]["subject"] == f"c{_stories.COMMITS_SHOWN + extra - 1}"
