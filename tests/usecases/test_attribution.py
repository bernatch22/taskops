"""The four guards on the identity inference, one test each.

This is the only place in taskops that decides who somebody is from data rather than from
what they said, so the guards are tested from the outside, at the level a caller can break
them: absent-vs-stated, agent-vs-dev, named-card-vs-pool, and recorded-vs-silent.
"""

from __future__ import annotations

from pathlib import Path

from taskops._clock import now
from taskops.storage import Store
from taskops.usecases import capture, init, plan
from taskops.usecases._project import attributed, project

AGENT = "agent:berna/api"


def _card(root: Path, *, assign: str) -> str:
    init(root, install_git_hooks=False)
    made = capture(root, "Wire the tool", spec="x", assign=assign, actor="dev:berna")
    return str(made["task"]["id"])


def _kinds(root: Path, task: str) -> list[str]:
    with project(root) as store:
        return [e["kind"] for e in store.events.of_task(task)]


def test_a_card_assigned_to_an_agent_speaks_for_a_caller_that_named_nobody(
        tmp_path: Path) -> None:
    task = _card(tmp_path, assign=AGENT)
    assert attributed(tmp_path, task, "") == AGENT


def test_the_inference_is_recorded_so_a_reader_can_tell_it_from_a_claim(
        tmp_path: Path) -> None:
    """Otherwise the log shows the agent acting and nothing distinguishes an attribution
    taskops MADE from one the agent stated — which is the whole risk of inferring at all."""
    task = _card(tmp_path, assign=AGENT)
    attributed(tmp_path, task, "")
    assert "inferred" in _kinds(tmp_path, task)


def test_a_stated_actor_is_never_overridden(tmp_path: Path) -> None:
    task = _card(tmp_path, assign=AGENT)
    assert attributed(tmp_path, task, "dev:ana") == "dev:ana"
    assert "inferred" not in _kinds(tmp_path, task)


def test_a_human_assignee_is_never_impersonated(tmp_path: Path) -> None:
    """A `dev:` on a card is a person, not a delegation. Speaking as them would write a
    human's name on work they never did, which no later correction undoes."""
    task = _card(tmp_path, assign="dev:ana")
    assert attributed(tmp_path, task, "") == ""
    assert "inferred" not in _kinds(tmp_path, task)


def test_a_pool_call_names_no_card_and_infers_nothing(tmp_path: Path) -> None:
    init(tmp_path, install_git_hooks=False)
    assert attributed(tmp_path, "", "") == ""


def test_an_unknown_card_falls_through_rather_than_raising(tmp_path: Path) -> None:
    """The real call is about to raise `NoSuchTask` with a message that names the fix;
    failing here first would replace it with one about identity."""
    init(tmp_path, install_git_hooks=False)
    assert attributed(tmp_path, "tk-nope", "") == ""


def test_the_marker_is_written_once_however_many_calls_follow(root: Path) -> None:
    """A worker makes twenty calls to finish a card. Twenty identical markers in a log whose
    whole value is a readable `git diff` would drown the events somebody is actually looking
    for — and the fact being recorded ("taskops named this agent on this card") is true once."""
    task = plan(root, [{"title": "the work"}], actor="dev:ana")["created"][0]["id"]
    with Store(root) as store:
        store.tasks.set_assignee(task, "agent:ana/api", when=now())

    for _ in range(5):
        assert attributed(root, task) == "agent:ana/api"

    with Store(root) as store:
        markers = store.events.of_task(task, kinds=("inferred",))
    assert len(markers) == 1


def test_a_second_agent_on_the_same_card_gets_its_own_marker(root: Path) -> None:
    """Once per card AND actor: a card reassigned to somebody else is a new attribution, and
    collapsing the two would hide exactly the handover a reader is looking for."""
    task = plan(root, [{"title": "the work"}], actor="dev:ana")["created"][0]["id"]
    with Store(root) as store:
        store.tasks.set_assignee(task, "agent:ana/api", when=now())
    attributed(root, task)
    with Store(root) as store:
        store.tasks.set_assignee(task, "agent:ana/ui", when=now())
    attributed(root, task)

    with Store(root) as store:
        markers = store.events.of_task(task, kinds=("inferred",))
    assert {m["actor"] for m in markers} == {"agent:ana/api", "agent:ana/ui"}
