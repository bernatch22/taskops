"""scripts/migrate_v1.py against REAL bytes from the axion v1 production log.

Every fixture under tests/fixtures/axion-v1/ is extracted verbatim from
`bernardocastro-box:.../axion/.taskops/events.jsonl` (926 events, one file per
defect — see the scratchpad's MIGRATION.md of 2026-08-08). The script passed
its hand-written unit tests and still lost the chapter, the criteria, the
rules and every released note — which is why these tests read files, never
invented dicts.
"""

from __future__ import annotations

import json
import collections
from typing import Any
from pathlib import Path

from scripts import migrate_v1

from taskops.core import replay, review
from taskops.core.event import make
from taskops.core.types import Event

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "axion-v1"
V1_MS_EVENT_ID = "fe528b46d06f3ab1"  # the create event whose id IS the v1 milestone's identity
MS_ID = "ms-fe528b"


def lines_of(*names: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name in names:
        text = (FIXTURES / name).read_text(encoding="utf-8")
        out.extend(json.loads(line) for line in text.splitlines() if line.strip())
    out.sort(key=lambda e: e["ts"])  # stable, ts only — MIGRATION.md §4F
    return out


def mapped(*names: str) -> tuple[list[tuple[str, dict[str, Any]]], collections.Counter[str]]:
    lines = lines_of(*names)
    ctx = migrate_v1.prepare(lines)
    counts: collections.Counter[str] = collections.Counter()
    out: list[tuple[str, dict[str, Any]]] = []
    for v1 in lines:
        out.extend(migrate_v1.map_event(v1, ctx, counts))
    return out, counts


def folded(*names: str) -> replay.State:
    lines = lines_of(*names)
    ctx = migrate_v1.prepare(lines)
    counts: collections.Counter[str] = collections.Counter()
    events: list[Event] = []
    for v1 in lines:
        for kind, body in migrate_v1.map_event(v1, ctx, counts):
            events.append(make(v1["task"], v1["actor"], kind, body, v1["ts"]))
    return replay.fold(events)


def test_defect1a_the_65_edited_events_survive_and_none_is_unknown() -> None:
    out, counts = mapped("defect1-milestone.jsonl", "defect1-edited.jsonl")
    edited = [b for k, b in out if k == "edited"]
    assert len(edited) == 63
    assert not any("unknown" in key for key in counts)
    # the 2 field=reviewer events are dropped BY NAME, never eaten
    assert sum(n for key, n in counts.items() if "reviewer" in key and "dropped" in key) == 2
    # the one field=spec event keeps its `to` and loses v1's `from`
    specs = [b for b in edited if b["field"] == "spec"]
    assert len(specs) == 1 and specs[0]["to"] and "from" not in specs[0]
    # every field=milestone edit points at the NEW id, or 62 cards point at nothing
    ms_edits = [b for b in edited if b["field"] == "milestone"]
    assert len(ms_edits) == 62
    assert all(b["to"] == MS_ID for b in ms_edits)


def test_defect1b_the_real_chapter_arrives_whole() -> None:
    goal = (FIXTURES / "fixtures_goal.txt").read_text(encoding="utf-8")
    assert len(goal) == 4252  # the fixture itself, before trusting the fold
    state = folded("defect1-milestone.jsonl")
    assert list(state["milestones"]) == [MS_ID]  # ONE milestone, not five
    stone = state["milestones"][MS_ID]
    assert stone["title"] == "La imprenta de edges"
    assert stone["goal"] == goal  # not the 815-char first draft: op update→edit worked
    assert stone["branch"] == "ms/la-imprenta-de-edges"  # slug of the FINAL title
    assert stone["status"] == "open"


def test_defect2_cancelled_arrives_dropped_and_review_becomes_submitted() -> None:
    out, _ = mapped("defect2-status.jsonl")
    by_kind = collections.Counter(k for k, _ in out)
    assert by_kind["submitted"] == 21
    assert by_kind["released"] == 37  # 35 ready + 2 backlog
    assert ("status", {"to": "dropped"}) in out  # tk-935930, v1's one cancelled card

    # the 21 submitted give 19 cards a review Standing (core/review.py folds them)
    lines = lines_of("defect2-status.jsonl")
    ctx = migrate_v1.prepare(lines)
    threads: dict[str, list[Event]] = collections.defaultdict(list)
    counts: collections.Counter[str] = collections.Counter()
    for v1 in lines:
        for kind, body in migrate_v1.map_event(v1, ctx, counts):
            threads[v1["task"]].append(make(v1["task"], v1["actor"], kind, body, v1["ts"]))
    assert len(review.pending(threads)) == 19

    # the card v1 leaves awaiting a verdict keeps the flag (board-wide, only
    # tk-790332 survives — the full-log run verifies that; this fixture lacks
    # the later `done` events that clear the other 18)
    assert "tk-790332" in ctx.review_final
    # ...and a later close DOES clear it: shapes carries a real `done`
    both = lines_of("defect2-status.jsonl", "shapes-one-per-kind.jsonl")
    done_tasks = {v1["task"] for v1 in both if v1["kind"] == "done"}
    assert done_tasks and not (migrate_v1.prepare(both).review_final & done_tasks)


def test_defect3_all_12_released_notes_survive() -> None:
    out, _ = mapped("defect3-released.jsonl")
    notes = [b["note"] for k, b in out if k == "released"]
    assert len(notes) == 12 and all(notes)  # v1 writes `text`, not note/reason
    assert any(n.startswith("Recovered: assigned to agent:me/axion1") for n in notes)


def test_defect4a_acceptance_becomes_criteria_all_91_lines() -> None:
    lines = lines_of("defect4-acceptance.jsonl")
    ctx = migrate_v1.prepare(lines)
    counts: collections.Counter[str] = collections.Counter()
    got: dict[str, list[str]] = {}
    for v1 in lines:
        for kind, body in migrate_v1.map_event(v1, ctx, counts):
            assert (kind, body["field"]) == ("edited", "criteria")
            got[v1["task"]] = body["to"]
    assert len(got) == 23
    assert sum(len(c) for c in got.values()) == 91
    assert len(got["tk-935930"]) == 4
    assert got["tk-935930"][0].startswith("WHEN paper_realize corre para un book")


def test_defect4b_the_9_project_rules_reach_milestone_rules() -> None:
    state = folded("defect1-milestone.jsonl", "defect4-context.jsonl")
    rules = state["milestones"][MS_ID]["rules"]
    assert len(rules) == 9
    assert rules[0].startswith("Nada se promueve por backtest")
    assert state["milestones"][MS_ID]["goal"] != ""  # rules edits must not blank the goal
    # the 4 dated notes are dropped by name
    _, counts = mapped("defect1-milestone.jsonl", "defect4-context.jsonl")
    assert sum(n for key, n in counts.items() if "context" in key and "dropped" in key) == 4


def test_defect5_only_the_17_message_mentions_survive_and_that_is_correct() -> None:
    """82 v1 events carry mentions; all 65 handoffs name ONLY their assignee, so
    MENTIONS.md §5's companion-comment rule fires zero times. 17 is the truth,
    not a loss — the assignment itself carries the other 65."""
    out, _ = mapped("defect5-mentions.jsonl")
    with_mentions = [b for _, b in out if b.get("mentions")]
    assert len(with_mentions) == 17
    comments = [b for k, b in out if k == "comment"]
    assert len(comments) == 17 and all(b["text"] for b in comments)  # no empty companions
    assert collections.Counter(k for k, _ in out)["edited"] == 65  # the assignments


def test_kinds_dropped_by_design_are_counted_never_eaten() -> None:
    out, counts = mapped("kinds-dropped-by-design.jsonl")
    assert out == []
    named = {key: n for key, n in counts.items() if "dropped" in key}
    assert sum(named.values()) == 75  # 42 branch + 31 landed + 2 policy
    assert not any("unknown" in key for key in counts)


def test_the_pass_through_shapes_still_make_valid_v2_events() -> None:
    lines = lines_of("shapes-one-per-kind.jsonl")
    ctx = migrate_v1.prepare(lines)
    counts: collections.Counter[str] = collections.Counter()
    for v1 in lines:
        for kind, body in migrate_v1.map_event(v1, ctx, counts):
            make(v1["task"], v1["actor"], kind, body, v1["ts"])  # raises on a bad shape


def test_created_drops_v1_reviewer_and_lands_in_the_real_milestone() -> None:
    lines = lines_of("defect1-milestone.jsonl", "shapes-one-per-kind.jsonl")
    ctx = migrate_v1.prepare(lines)
    counts: collections.Counter[str] = collections.Counter()
    cards = [
        body["card"]
        for v1 in lines
        for kind, body in migrate_v1.map_event(v1, ctx, counts)
        if kind == "created"
    ]
    assert cards, "the shapes fixture carries a real created event"
    for card in cards:
        assert "reviewer" not in card
        assert card["milestone"] == MS_ID
        assert card["after"] == [] or isinstance(card["after"], list)


def test_a_second_run_is_a_no_op(tmp_path: Path) -> None:
    source = tmp_path / "events.jsonl"
    text = "\n".join(
        (FIXTURES / name).read_text(encoding="utf-8").strip()
        for name in ("defect1-milestone.jsonl", "shapes-one-per-kind.jsonl", "defect4-context.jsonl")
    )
    source.write_text(text, encoding="utf-8")
    board = tmp_path / "board"
    migrate_v1.migrate(source, board)
    once = (board / "events.jsonl").read_text(encoding="utf-8")
    migrate_v1.migrate(source, board)
    assert (board / "events.jsonl").read_text(encoding="utf-8") == once
