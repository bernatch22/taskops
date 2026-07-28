"""The context layer: what stays in force, what falls out, and what two clones agree on.

Four properties earn their test here, and each one is a way the layer would fail SILENTLY:
a supersede that ate its predecessor, a slice that dropped an invariant, a retire that
deleted, and a tie two machines broke differently. None of them raise; they just make the
next agent work from something slightly wrong, which is the whole failure mode the context
layer exists to remove.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskops._errors import BadRequest
from taskops.contracts.context import CONTEXT_KIND, CONTEXT_TASK
from taskops.engine.log import build
from taskops.storage import Store
from taskops.storage.context import facts
from taskops.usecases._contextslice import for_task, in_force
from taskops.usecases.context import context_for, history, retire, show, state
from taskops.usecases.plan import plan

NEVER = "never Co-Authored-By in a commit"


def test_a_new_objective_supersedes_without_erasing(root: Path) -> None:
    """Superseding is a NEWER event, never an edit of the old one. `show` moves on; the log
    remembers — which is the whole reason this is a log and not a config file."""
    first = state(root, "objective", "ship the context layer")
    second = state(root, "objective", "ship 0.4")
    current = show(root)["objective"]
    assert current is not None and current["id"] == second["id"]
    assert [f["text"] for f in history(root)] == [first["text"], second["text"]]


def test_a_retired_fact_leaves_show_and_stays_in_the_log(root: Path) -> None:
    """`retire` retires. An append-only log has no eraser, so the fact is still there,
    flagged — otherwise "why did we stop doing this" has no answer six months later."""
    fact = state(root, "invariant", NEVER)
    retire(root, fact["id"])
    assert show(root)["invariants"] == []
    logged = history(root)
    assert [f["id"] for f in logged] == [fact["id"]]
    assert logged[0]["retired"] is True


def test_retiring_something_that_was_never_stated_says_so(root: Path) -> None:
    with pytest.raises(BadRequest) as raised:
        retire(root, "nope")
    assert "context log" in str(raised.value)


def test_an_invariant_is_never_filtered_out_of_a_slice(root: Path) -> None:
    """The load-bearing asymmetry: a decision that misses a card costs a re-litigation, an
    invariant that misses one costs the breakage it existed to prevent. So scope narrows
    decisions and never invariants — including one whose labels match nothing on the card."""
    state(root, "invariant", NEVER)
    state(root, "invariant", "SQL only in storage/", labels=["storage"])
    state(root, "decision", "sqlite, not postgres", labels=["storage"])
    task = plan(root, [{"title": "render the board", "labels": ["ui"], "files": ["src/ui.py"]}])
    view = context_for(root, task["created"][0]["id"])
    assert {f["text"] for f in view["invariants"]} == {NEVER, "SQL only in storage/"}
    assert view["decisions"] == []


def test_a_decision_reaches_a_card_by_label_or_by_edit_surface(root: Path) -> None:
    """Two ways in, plus the unscoped fact that reaches everything: a decision with no scope
    is a project-wide one, and demanding a label for it would leave it reaching nothing."""
    state(root, "decision", "labelled", labels=["storage"])
    state(root, "decision", "by file", files=["src/taskops/storage"])
    state(root, "decision", "unscoped")
    state(root, "decision", "elsewhere", labels=["ui"], files=["src/ui.py"])
    made = plan(root, [{"title": "add a table", "labels": ["storage"],
                        "files": ["src/taskops/storage/_ddl.py"]}])
    texts = {f["text"] for f in context_for(root, made["created"][0]["id"])["decisions"]}
    assert texts == {"labelled", "by file", "unscoped"}


def test_two_clones_break_a_tie_the_same_way(root: Path, tmp_path: Path) -> None:
    """The split-brain test. Two machines add an objective offline at the SAME timestamp, then
    exchange events in opposite orders. `(ts, id)` decides, and `id` is the content hash — the
    same number on both — so both elect the same winner. Ordering by arrival would give each
    clone its own answer, and no supervisor could tell they disagreed.
    """
    at = 1_800_000_100.0
    mine = build(task=CONTEXT_TASK, actor="dev:a", kind=CONTEXT_KIND, ts=at,
                 body={"sort": "objective", "text": "ship 0.4"})
    theirs = build(task=CONTEXT_TASK, actor="dev:b", kind=CONTEXT_KIND, ts=at,
                   body={"sort": "objective", "text": "ship 0.5"})
    assert mine["ts"] == theirs["ts"] and mine["id"] != theirs["id"]
    other = tmp_path / "clone"
    (other / ".taskops").mkdir(parents=True)
    elected = [_winner_after(where, order)
               for where, order in ((root, [mine, theirs]), (other, [theirs, mine]))]
    assert elected[0] == elected[1]


def _winner_after(where: Path, events: list[dict]) -> str:  # type: ignore[type-arg]
    """Apply a log in one arrival order and report which objective is in force."""
    with Store(where) as store:
        for event in events:
            store.events.append(event)          # type: ignore[arg-type]
        current = in_force(facts(store))["objective"]
    return "" if current is None else current["text"]


def test_the_slice_is_pure_and_survives_a_card_with_no_scope() -> None:
    """`for_task` takes facts and a task, no store — which is why a card with neither labels
    nor files can be tested from literals, and why it still gets every invariant."""
    live = [_fact("i", "invariant"), _fact("d", "decision", labels=["ui"])]
    bare = {"labels": [], "files": []}
    view = for_task(live, bare)                 # type: ignore[arg-type]
    assert len(view["invariants"]) == 1 and view["decisions"] == []


def test_a_fact_with_no_text_is_refused(root: Path) -> None:
    with pytest.raises(BadRequest):
        state(root, "invariant", "   ")


def test_an_unknown_sort_is_refused_before_anything_is_written(root: Path) -> None:
    with pytest.raises(BadRequest) as raised:
        state(root, "vibe", "be nice")
    assert "objective" in str(raised.value)


def _fact(name: str, sort: str, *, labels: list[str] | None = None) -> dict:  # type: ignore[type-arg]
    return {"id": name, "sort": sort, "text": name, "labels": labels or [], "files": [],
            "horizon": "", "owner": "", "actor": "dev:a", "ts": 1.0, "retired": False}
