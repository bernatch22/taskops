"""Dispatch: assignment, the dry run, and the rules that stop a worker taking the wrong card.

The LAUNCH itself is not tested here — it starts a real Claude Code, which costs money and needs a
network, so it was verified by hand instead (two workers coded, committed and closed their cards
unsupervised). What IS tested is everything around it, including the two bugs that live fleet found: a
worker claiming a card assigned to somebody else, and the need for a preview that changes nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskops.storage import Store
from taskops.usecases import board, dispatch, init, next_task, plan
from taskops.usecases.dispatch import DEFAULT_WORKERS, MAX_WORKERS


@pytest.fixture
def project(tmp_path: Path) -> Path:
    init(tmp_path, install_git_hooks=False)
    plan(tmp_path, [{"title": "A", "spec": "a", "files": ["a.py"]},
                    {"title": "B", "spec": "b", "files": ["b.py"]},
                    {"title": "C", "spec": "c", "files": ["c.py"]}], actor="dev:berna")
    return tmp_path


def assign(project: Path, task_id: str, actor: str) -> None:
    """Assign without launching: the state dispatch leaves behind, minus the process."""
    with Store(project) as store:
        store.tasks.set_assignee(task_id, actor, when=1.0)


def first_ready(project: Path) -> str:
    return dispatch(project, count=1, dry_run=True, actor="dev:berna").launched[0].task


# ---- the dry run


def test_a_dry_run_changes_nothing(project: Path) -> None:
    """THE reason it exists: this is the one call in taskops that spends money, so looking first has
    to be free — and a preview that assigned cards would be worse than no preview at all."""
    preview = dispatch(project, count=2, dry_run=True, actor="dev:berna")
    assert preview.planned is True
    assert len(preview.launched) == 2
    assert all(w.pid == 0 for w in preview.launched), "a preview must have no processes"

    for column in board(project)["columns"]:
        for card in column["cards"]:
            assert card["task"]["assignee"] == "", "the dry run assigned a card"


def test_a_dry_run_names_the_workers_it_would_start(project: Path) -> None:
    """The names are derived, not random, so a planner can predict what its fleet will look like."""
    preview = dispatch(project, count=3, prefix="api", dry_run=True, actor="dev:berna")
    assert [w.actor for w in preview.launched] == ["agent:berna/api1", "agent:berna/api2",
                                                  "agent:berna/api3"]


def test_the_default_count_is_conservative(project: Path) -> None:
    """Three, not "everything ready": every worker is a model, and a first try on a real repository
    should not turn into a stampede."""
    assert len(dispatch(project, dry_run=True, actor="dev:berna").launched) == DEFAULT_WORKERS


def test_asking_for_more_than_the_ceiling_is_refused(tmp_path: Path) -> None:
    """A planner that miscounts should hit a refusal here rather than an invoice later."""
    from taskops import BadRequest

    init(tmp_path, install_git_hooks=False)
    made = plan(tmp_path, [{"title": f"T{i}", "spec": "x"} for i in range(MAX_WORKERS + 1)],
                actor="dev:berna")
    with pytest.raises(BadRequest) as caught:
        dispatch(tmp_path, tasks=tuple(t["id"] for t in made["created"]),
                 dry_run=True, actor="dev:berna")
    assert "ceiling" in str(caught.value)


# ---- assignment, and the bug the live fleet found


def test_an_assigned_card_is_invisible_to_another_agent(project: Path) -> None:
    """Assignment FILTERS the pool. Without it, "this one is yours" is a label anybody ignores."""
    target = first_ready(project)
    assign(project, target, "agent:berna/w1")

    other = next_task(project, actor="agent:ana/intruder")
    assert other["claim"] is not None
    assert other["claim"]["view"]["task"]["id"] != target, "an intruder was handed an assigned card"


def test_an_assigned_card_cannot_be_claimed_by_id_either(project: Path) -> None:
    """THE bug a live fleet found. Filtering the ready pool was not enough, because asking BY ID
    never went through it — so a worker that had invented its own actor id took another's card."""
    target = first_ready(project)
    assign(project, target, "agent:berna/w1")

    refused = next_task(project, actor="agent:ana/intruder", task=target)
    assert refused["claim"] is None
    assert "agent:berna/w1" in refused["reason"], "the reason must name who it belongs to"


def test_the_assignee_can_still_claim_its_own_card(project: Path) -> None:
    """The other half of the same rule: filtering must not lock out the worker it was assigned TO,
    which is the whole point of dispatch assigning before it launches."""
    target = first_ready(project)
    assign(project, target, "agent:berna/w1")

    mine = next_task(project, actor="agent:berna/w1", task=target)
    assert mine["claim"] is not None
    assert mine["claim"]["view"]["task"]["id"] == target


def test_an_assigned_card_is_not_dispatched_twice(project: Path) -> None:
    """Re-dispatching would start a second worker on a card the first one is already doing."""
    target = first_ready(project)
    assign(project, target, "agent:berna/w1")

    result = dispatch(project, tasks=(target,), dry_run=True, actor="dev:berna")
    assert result.launched == []
    assert target in result.skipped


def test_dispatching_a_blocked_card_is_refused_not_launched(tmp_path: Path) -> None:
    """A worker started on a blocked card finds nothing to do and exits, which reads as a broken
    dispatch rather than as the wrong request it was."""
    init(tmp_path, install_git_hooks=False)
    made = plan(tmp_path, [{"title": "first", "spec": "x"},
                           {"title": "second", "spec": "y", "after": [0]}],
                actor="dev:berna")
    blocked = made["created"][1]["id"]

    result = dispatch(tmp_path, tasks=(blocked,), dry_run=True, actor="dev:berna")
    assert result.launched == []
    assert blocked in result.skipped


def test_nothing_to_dispatch_says_so(tmp_path: Path) -> None:
    """An empty board is not an error, and a dispatch that returned nothing with no explanation is
    how somebody concludes the tool is broken."""
    from taskops.render import render_dispatch

    init(tmp_path, install_git_hooks=False)
    result = dispatch(tmp_path, dry_run=True, actor="dev:berna")
    assert result.launched == []
    assert "nothing to dispatch" in render_dispatch(result)


def test_the_render_says_loudly_that_nothing_started(project: Path) -> None:
    """A preview that reads like a result is how a planner believes five agents are working when none
    are — so the heading says it, and the pid column carries no numbers."""
    from taskops.render import render_dispatch

    text = render_dispatch(dispatch(project, count=2, dry_run=True, actor="dev:berna"))
    assert "NOTHING STARTED" in text
    assert "no process started" in text
