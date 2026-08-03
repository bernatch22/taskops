"""Dispatch: assignment, the dry run, and the rules that stop a worker taking the wrong card.

The LAUNCH itself is not tested here — it starts a real Claude Code, which costs money and needs a
network, so it was verified by hand instead (two workers coded, committed and closed their cards
unsupervised). What IS tested is everything around it, including the two bugs that live fleet found: a
worker claiming a card assigned to somebody else, and the need for a preview that changes nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskops._errors import BadRequest
from taskops.storage import Store
from taskops.usecases import board, dispatch, init, next_task, plan
from taskops.usecases.dispatch import DEFAULT_WORKERS, MAX_WORKERS
from taskops.usecases.milestone import open_chapter


@pytest.fixture
def project(tmp_path: Path) -> Path:
    # Every card belongs to a chapter: the fixture opens one so the test can be about its own
    # subject rather than about that.
    init(tmp_path, install_git_hooks=False)
    open_chapter(tmp_path, "the chapter these tests plan into",
                 actor="dev:berna")
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
    open_chapter(tmp_path, "the chapter these tests plan into",
                 actor="dev:berna")
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


def test_a_card_assigned_to_a_developer_is_claimable_by_that_developers_worker(
        project: Path) -> None:
    """The delegation path, and it was refused end to end: assign a card to a PERSON, that
    person's session spawns a worker, and the worker was told the card was somebody else's.

    All four rows of the rule are here because only the pair says anything. `agent:ana/w1` is
    `dev:ana` with one more hand, so it must be let in; `dev:juan` and its workers must not be,
    or "assigned" stops meaning anything at all.
    """
    target = first_ready(project)
    assign(project, target, "dev:ana")

    for stranger in ("agent:juan/w1", "dev:juan"):
        refused = next_task(project, actor=stranger, task=target)
        assert refused["claim"] is None, f"{stranger} took a card assigned to dev:ana"
        assert "dev:ana" in refused["reason"]

    mine = next_task(project, actor="agent:ana/w1", task=target)
    assert mine["claim"] is not None, "a worker was refused the card dispatched to its dev"
    assert mine["claim"]["view"]["task"]["id"] == target


def test_the_developer_the_card_names_can_still_claim_it_directly(project: Path) -> None:
    """The other hand of the same person: folding the agent in must not push the dev out."""
    target = first_ready(project)
    assign(project, target, "dev:ana")

    mine = next_task(project, actor="dev:ana", task=target)
    assert mine["claim"] is not None
    assert mine["claim"]["view"]["task"]["id"] == target


def test_a_card_dispatched_to_a_worker_stays_that_workers_own(project: Path) -> None:
    """The fold goes ONE way. An `agent:` assignee is a specific worker's card — its developer
    reaching in would be taking work mid-flight, and the sibling worker case is theft outright.
    """
    target = first_ready(project)
    assign(project, target, "agent:ana/w1")

    for other in ("dev:ana", "agent:ana/w2"):
        refused = next_task(project, actor=other, task=target)
        assert refused["claim"] is None, f"{other} reached into agent:ana/w1's card"


def test_the_pool_offers_a_developers_card_to_that_developers_worker(project: Path) -> None:
    """The POOL half of the same bug, and it had it too: a worker asking for "anything" was not
    offered the card its own developer had been handed, while a stranger's worker was correctly
    not offered it either. Filtering by actor id hid a person's work from their own hands.
    """
    target = first_ready(project)
    assign(project, target, "dev:ana")

    stranger = next_task(project, actor="agent:juan/w1")
    assert stranger["claim"] is not None
    assert stranger["claim"]["view"]["task"]["id"] != target, "an intruder was handed it"

    mine = next_task(project, actor="agent:ana/w1")
    assert mine["claim"] is not None
    assert mine["claim"]["view"]["task"]["id"] == target, "own work sorts first, and is offered"


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
    open_chapter(tmp_path, "the chapter these tests plan into",
                 actor="dev:berna")
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
    open_chapter(tmp_path, "the chapter these tests plan into",
                 actor="dev:berna")
    result = dispatch(tmp_path, dry_run=True, actor="dev:berna")
    assert result.launched == []
    assert "nothing to dispatch" in render_dispatch(result)


def test_the_render_says_loudly_that_nothing_started(project: Path) -> None:
    """A preview that reads like a result is how a planner believes five agents are working when none
    are — so the heading says it, and the pid column carries no numbers."""
    from taskops.render import render_dispatch

    text = render_dispatch(dispatch(project, count=2, dry_run=True, actor="dev:berna"))
    assert "NOTHING STARTED" in text
    assert "nothing started" in text


def test_the_default_mode_prepares_briefs_and_starts_nothing(project: Path) -> None:
    """THE correction. The first version spawned `claude -p` per card, which opens a NEW billed
    session each time — a fleet of six drained an API balance mid-run and left six cards claimed by
    processes that no longer existed. The default now assigns, makes the worktree, and hands back a
    brief for the caller to spawn as a sub-agent on the session it already pays for.
    """
    from taskops.render import render_dispatch

    result = dispatch(project, count=2, actor="dev:berna")
    assert result.spawned is False
    assert all(w.pid == 0 for w in result.launched), "the default mode started a process"
    assert all(w.brief for w in result.launched), "a prepared worker with no brief is unusable"

    text = render_dispatch(result)
    assert "SPAWN THEM BELOW" in text
    assert "IN THIS SESSION" in text


def test_a_brief_tells_the_subagent_its_worktree_and_not_to_switch(project: Path) -> None:
    """The two lines that make parallel branches possible with sub-agents.

    A sub-agent SHARES the parent's working directory, so without being told a path it edits `main`,
    and a `git switch` in a shared checkout moves the branch under every other worker at once. That
    is the failure that makes people conclude parallel agents cannot use separate branches.
    """
    result = dispatch(project, count=1, actor="dev:berna")
    brief = result.launched[0].brief
    assert str(result.launched[0].tree) in brief
    assert "never run `git switch`" in brief
    assert f"Task: {result.launched[0].task}" in brief, "no trailer means no commit binding"


def test_preparing_assigns_the_card(project: Path) -> None:
    """Assignment happens even without a process, or a sub-agent could be handed a card another
    agent takes first."""
    result = dispatch(project, count=1, actor="dev:berna")
    from taskops.usecases import ask

    assert ask(project, result.launched[0].task)["task"]["assignee"] == result.launched[0].actor


# ---- routing to a registered specialist


def register(project: Path, name: str, labels: str) -> None:
    folder = project / ".claude" / "agents"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: a specialist\nlabels: [{labels}]\n---\n\nwork\n",
        encoding="utf-8")


def test_a_dispatched_card_names_the_specialist_it_belongs_to(tmp_path: Path) -> None:
    """taskops routes; the CALLER spawns. The name has to reach the brief, because the host
    session is the only thing that can act on it."""
    init(tmp_path, install_git_hooks=False)
    open_chapter(tmp_path, "the chapter these tests plan into",
                 actor="dev:berna")
    register(tmp_path, "taskops-collectors", "etl")
    plan(tmp_path, [{"title": "fix the loader", "spec": "x", "labels": ["etl"]}],
         actor="dev:berna")

    worker = dispatch(tmp_path, count=1, actor="dev:berna").launched[0]
    assert worker.agent_type == "taskops-collectors"
    assert "agent_type: taskops-collectors" in worker.brief


def test_without_a_registry_nothing_about_dispatch_changes(project: Path) -> None:
    """The regression guard: no `.claude/agents/`, no agent type, and a brief that reads
    exactly as it did before this card existed."""
    worker = dispatch(project, count=1, actor="dev:berna").launched[0]
    assert worker.agent_type == ""
    assert "agent_type" not in worker.brief


def test_an_after_naming_nothing_is_refused_rather_than_silently_flat(tmp_path: Path) -> None:
    """`_resolve` promises a dependency never silently fails to apply. It kept that for indexes
    and broke it for strings: anything not an int fell through to "it is an id", `deps` has no
    foreign key, and `open_blockers_of` JOINs on `tasks` — so an edge to a task that does not
    exist blocks nothing while the card reads as wired.

    Found by writing `after: "0,1"`, which is the shape `tasks add --after` takes on the command
    line: the board showed a card depending on something and offered it to three workers at once.
    """
    init(tmp_path, install_git_hooks=False)
    open_chapter(tmp_path, "the chapter these tests plan into",
                 actor="dev:berna")

    with pytest.raises(BadRequest, match="not a task in this batch"):
        plan(tmp_path, [{"title": "one", "spec": "s"}, {"title": "two", "spec": "s"},
                        {"title": "last", "spec": "s", "after": "0,1"}], actor="dev:berna")

    created = plan(tmp_path, [{"title": "one", "spec": "s"}, {"title": "two", "spec": "s"},
                              {"title": "last", "spec": "s", "after": [0, 1]}],
                   actor="dev:berna")["created"]
    assert board(tmp_path)["ready"] == 2, "the third waits on both, as written"
    assert created[2]["status"] == "backlog"
