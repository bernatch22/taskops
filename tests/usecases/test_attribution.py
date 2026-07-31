"""The four guards on the identity inference, one test each.

This is the only place in taskops that decides who somebody is from data rather than from
what they said, so the guards are tested from the outside, at the level a caller can break
them: absent-vs-stated, agent-vs-dev, named-card-vs-pool, and recorded-vs-silent.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

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


def test_the_account_beats_git_because_an_agent_can_rewrite_git(tmp_path: Path,
                                                                monkeypatch: Any) -> None:
    """git config used to come straight after `$TASKOPS_ACTOR`, and an agent rewrote
    `user.email` on a lab checkout — because that repository's own CLAUDE.md told it which git
    identity to use — so a whole developer silently became somebody else mid-run. Two clones
    drifting to the same name would deadlock `reviewer: peer`: the only actor allowed to close
    would be the author. `$USER` is not something an agent edits in passing."""
    from taskops.engine.identity import resolve

    monkeypatch.delenv("TASKOPS_ACTOR", raising=False)
    monkeypatch.delenv("GITHUB_USER", raising=False)
    monkeypatch.setenv("USER", "berna")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "config", "user.email", "somebody-else@example.com"],
                   cwd=tmp_path, check=True)

    assert resolve(tmp_path)["id"] == "dev:berna"


def test_an_explicit_actor_still_wins_over_the_account(tmp_path: Path,
                                                       monkeypatch: Any) -> None:
    """The one place this differs from how it was asked for, and the reason is the lab itself:
    two sessions on one machine SHARE a `$USER`. If the account won, `dev:uno` and `dev:dos`
    would be the same person and peer review would have nobody to hand a card to."""
    from taskops.engine.identity import resolve

    monkeypatch.setenv("USER", "berna")
    monkeypatch.setenv("TASKOPS_ACTOR", "dev:dos")

    assert resolve(tmp_path)["id"] == "dev:dos"


def test_an_account_name_git_would_refuse_is_normalised_not_dropped(tmp_path: Path,
                                                                    monkeypatch: Any) -> None:
    """`$USER` can hold a dot, a space, a domain slash. Refusing those would fall back to git —
    the source this ordering exists to demote — so it is filed under the closest legal name."""
    from taskops.engine.identity import resolve

    monkeypatch.delenv("TASKOPS_ACTOR", raising=False)
    monkeypatch.delenv("GITHUB_USER", raising=False)
    monkeypatch.setenv("USER", "CORP\\Ana Diaz")

    assert resolve(tmp_path)["id"] == "dev:corp-ana-diaz"
