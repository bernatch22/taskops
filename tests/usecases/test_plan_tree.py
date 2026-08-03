"""A plan's two relations, and the convention they now share.

`parent` is the TREE ("what is this part of"), `after` is the DAG ("what must happen first").
The contract has always said so; what it did not say is that only one of them accepted an index
into the batch. `after: 0` worked, `parent: 0` was read as "not a string", dropped to `None`,
and the call answered `# planned 3 task(s)` about a tree that did not exist.

That silence is the bug these tests exist for. A refusal is fine — a plan a person can fix. A
plan that reports success and builds something flatter than what was asked for is the expensive
kind of wrong, because nothing about it looks wrong: the board reads as decomposed, the epic's
`done` guard has nothing to count, and it closes over unfinished work.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskops._errors import BadRequest, GuardFailed
from taskops.storage import Store
from taskops.usecases import ask, init, next_task, plan, update
from taskops.usecases.milestone import open_chapter


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    # Every card belongs to a chapter: the fixture opens one so the test can be about its own
    # subject rather than about that.
    init(tmp_path, install_git_hooks=False)
    open_chapter(tmp_path, "the chapter these tests plan into",
                 actor="dev:berna")
    return tmp_path


def tree(repo: Path) -> dict[str, str | None]:
    """`title -> parent title`, which is the shape the assertion is actually about."""
    with Store(repo) as store:
        rows = store.db.execute("SELECT id, parent, title FROM tasks").fetchall()
    titles = {row["id"]: row["title"] for row in rows}
    return {row["title"]: titles.get(row["parent"]) for row in rows}


# ---- the tree, in one call


def test_a_parent_may_be_an_index_into_the_same_batch(repo: Path) -> None:
    """THE regression. It used to answer "planned 3" and build three loose cards."""
    plan(repo, [{"title": "EPIC"}, {"title": "one", "parent": 0}, {"title": "two", "parent": 0}],
         actor="dev:ana")

    assert tree(repo) == {"EPIC": None, "one": "EPIC", "two": "EPIC"}


def test_three_levels_land_in_one_call(repo: Path) -> None:
    """The shape the fix is for: an epic, its subtasks, and their checklist — planned once.

    Depth is not special-cased anywhere; it falls out of resolving against ids minted before the
    first insert, so a grandchild can name a parent created two entries earlier in the batch.
    """
    plan(repo, [{"title": "EPIC"},
                {"title": "reader", "parent": 0},
                {"title": "open the file", "parent": 1},
                {"title": "iterate lazily", "parent": 1}], actor="dev:ana")

    assert tree(repo) == {"EPIC": None, "reader": "EPIC",
                          "open the file": "reader", "iterate lazily": "reader"}


def test_the_tree_and_the_dag_are_wired_by_the_same_call_and_do_not_interfere(
        repo: Path) -> None:
    """Two relations, two answers. A child is READY the moment it is created — an epic does not
    block what it contains — while an `after` holds its dependent in `backlog`."""
    made = plan(repo, [{"title": "EPIC"},
                       {"title": "reader", "parent": 0},
                       {"title": "validator", "parent": 0, "after": [1]}],
                actor="dev:ana")["created"]

    status = {task["title"]: ask(repo, task["id"])["task"]["status"] for task in made}
    assert status == {"EPIC": "ready", "reader": "ready", "validator": "backlog"}


def test_a_parent_may_still_be_an_id_from_an_earlier_call(repo: Path) -> None:
    """The two-call shape has to keep working: it is what every existing plan does."""
    epic = plan(repo, [{"title": "EPIC"}], actor="dev:ana")["created"][0]["id"]
    plan(repo, [{"title": "one", "parent": epic}], actor="dev:ana")

    assert tree(repo)["one"] == "EPIC"


def test_naming_nobody_is_still_naming_nobody(repo: Path) -> None:
    plan(repo, [{"title": "loose"}, {"title": "also loose", "parent": ""}], actor="dev:ana")
    assert tree(repo) == {"loose": None, "also loose": None}


# ---- and every way of getting it wrong is REFUSED, never dropped


def test_a_card_that_is_its_own_parent_is_refused(repo: Path) -> None:
    """One keystroke from correct, and the result is an epic nothing can ever close: it is
    permanently its own open subtask."""
    with pytest.raises(BadRequest) as refused:
        plan(repo, [{"title": "EPIC", "parent": 0}], actor="dev:ana")
    assert "its own `parent`" in str(refused.value)


def test_an_index_outside_the_batch_is_refused_naming_the_size(repo: Path) -> None:
    with pytest.raises(BadRequest) as refused:
        plan(repo, [{"title": "a"}, {"title": "b", "parent": 9}], actor="dev:ana")
    assert "outside this batch of 2" in str(refused.value)


def test_an_id_no_board_knows_is_refused(repo: Path) -> None:
    with pytest.raises(BadRequest) as refused:
        plan(repo, [{"title": "a", "parent": "tk-nobody"}], actor="dev:ana")
    assert "not a task in this batch" in str(refused.value)


def test_true_is_not_the_first_entry(repo: Path) -> None:
    """`True == 1` in Python, so a `parent: true` would silently adopt the first card."""
    with pytest.raises(BadRequest) as refused:
        plan(repo, [{"title": "a"}, {"title": "b", "parent": True}], actor="dev:ana")
    assert "expected an index or a task id" in str(refused.value)


def test_nothing_is_created_when_one_entry_is_refused(repo: Path) -> None:
    """A partly-created plan is worse than none: the caller re-runs it and gets duplicates of
    everything that did land."""
    with pytest.raises(BadRequest):
        plan(repo, [{"title": "a"}, {"title": "b", "parent": 9}], actor="dev:ana")
    with Store(repo) as store:
        assert store.db.execute("SELECT COUNT(*) AS n FROM tasks").fetchone()["n"] == 0


# ---- what the tree is FOR


def test_the_epic_cannot_close_over_an_unfinished_child(repo: Path) -> None:
    """The reason `parent` is worth resolving at all. With the index silently dropped, this
    epic had no children to count and closed over work nobody had done."""
    made = plan(repo, [{"title": "EPIC"}, {"title": "one", "parent": 0}],
                actor="dev:ana")["created"]
    epic = made[0]["id"]
    next_task(repo, task=epic, actor="agent:ana/w1")

    with pytest.raises(GuardFailed) as refused:
        update(repo, epic, status="done", comment="listo", actor="agent:ana/w1", no_code=True)
    assert "open subtask" in str(refused.value)


def test_the_card_lists_its_children(repo: Path) -> None:
    made = plan(repo, [{"title": "EPIC"}, {"title": "one", "parent": 0}],
                actor="dev:ana")["created"]
    assert [child["title"] for child in ask(repo, made[0]["id"])["children"]] == ["one"]


def test_a_child_names_the_epic_it_is_part_of(repo: Path) -> None:
    """The other direction of the tree, which did not exist.

    A parent listed its children from the day `parent` did; a child named nothing. So a worker
    inside a three-level plan could not learn what the thing it was building was FOR — not from
    its card, and not from the brief `dispatch` writes, which never mentions an epic either. A
    spec read without that is how a subtask gets solved correctly for the wrong problem.

    The epic is RESOLVED, not left as an id: `task.parent` was always on the wire and it is a
    hex string, which is not something anybody can read.
    """
    made = plan(repo, [{"title": "EPIC", "spec": "join the parts"},
                       {"title": "one", "parent": 0}], actor="dev:ana")["created"]

    child = ask(repo, made[1]["id"])
    assert child["epic"] is not None
    assert child["epic"]["title"] == "EPIC"
    assert ask(repo, made[0]["id"])["epic"] is None, "and a loose card is part of nothing"


def test_the_card_a_worker_reads_says_what_it_is_part_of(repo: Path) -> None:
    """Rendered, because the payload having it is not the same as an agent seeing it: a worker
    reads the markdown `taskops_next` prints, not the JSON underneath."""
    from taskops.render import render_view

    made = plan(repo, [{"title": "EPIC", "spec": "join the parts"},
                       {"title": "one", "parent": 0}], actor="dev:ana")["created"]

    shown = render_view(ask(repo, made[1]["id"]))
    assert f"### Part of {made[0]['id']} — EPIC" in shown
    assert "join the parts" in shown, "the epic's spec too — that is what makes the child's read"
