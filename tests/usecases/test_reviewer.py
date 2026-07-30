"""The reviewer a card names when it is created — the field, the default, and the refusal.

Two halves, tested where each one lives. Naming is a USE CASE: what a bare name means, what
happens when it is not a specialist this project has, and where the project's default comes
from. Enforcement is a GUARD, so it is tested from literals — a card that names a person
refuses `done` from every agent, and a card that names nobody behaves exactly as it did
before this existed, which is the regression the whole feature must not cost.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskops import BadRequest
from taskops._errors import GuardFailed
from taskops._types import HUMAN
from taskops.contracts import Task
from taskops.engine.machine import Facts, check_move
from taskops.render import render_view
from taskops.usecases import ask, edit, init, plan
from taskops.usecases.context import state
from tests.conftest import CLOCK
from tests.usecases.test_agents import COLLECTORS, write_agent


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A project that has ONE registered specialist, `taskops-collectors`."""
    init(tmp_path, install_git_hooks=False)
    write_agent(tmp_path, "taskops-collectors", COLLECTORS)
    return tmp_path


def card(project: Path, **entry: object) -> Task:
    return plan(project, [{"title": "t", **entry}])["created"][0]


# ---- naming a reviewer


def test_a_registered_specialist_is_kept_as_written(project: Path) -> None:
    """The stored value is the registry name, because that is what a host spawns."""
    assert card(project, reviewer="taskops-collectors")["reviewer"] == "taskops-collectors"


def test_a_bare_name_that_is_not_a_specialist_is_refused_naming_the_ones_there_are(
        project: Path) -> None:
    """A typo here is a card nothing can ever close and nothing on the board says why —
    the same reason assignment refuses an unknown bare name."""
    with pytest.raises(BadRequest) as caught:
        card(project, reviewer="taskops-collectrs")
    assert "taskops-collectors" in str(caught.value)


def test_human_is_accepted_as_typed(project: Path) -> None:
    """It is what somebody writes for "whoever is reading the board", and it is NOT
    normalised into a `dev:` id nobody chose."""
    assert card(project, reviewer=HUMAN)["reviewer"] == HUMAN


def test_a_person_is_never_checked_against_the_registry(project: Path) -> None:
    """`dev:ana` addresses somebody who was never going to be in a registry."""
    assert card(project, reviewer="dev:ana")["reviewer"] == "dev:ana"
    assert card(project, reviewer="agent:ana/scratch")["reviewer"] == "agent:ana/scratch"


def test_a_card_that_names_nobody_stores_nothing(project: Path) -> None:
    assert card(project)["reviewer"] == ""


# ---- the default, which is a project DECISION and not a constant


def test_the_project_decision_supplies_the_default(project: Path) -> None:
    state(project, "decision", "reviewer: taskops-collectors")
    assert card(project)["reviewer"] == "taskops-collectors"


def test_an_explicit_reviewer_beats_the_default(project: Path) -> None:
    state(project, "decision", "reviewer: taskops-collectors")
    assert card(project, reviewer=HUMAN)["reviewer"] == HUMAN


def test_a_default_naming_nobody_real_degrades_instead_of_breaking_planning(project: Path) -> None:
    """A typo in one project-wide decision must not make every `plan` call fail — that
    would take the board down for a sentence somebody wrote by hand."""
    state(project, "decision", "reviewer: nobody-registered")
    assert card(project)["reviewer"] == ""


def test_a_decision_about_something_else_is_not_read_as_a_reviewer(project: Path) -> None:
    state(project, "decision", "we deploy on Fridays")
    assert card(project)["reviewer"] == ""


# ---- editing it


def test_a_reviewer_can_be_named_later_and_cleared(project: Path) -> None:
    task = card(project)
    assert edit(project, task["id"], reviewer="taskops-collectors")["changed"] == ["reviewer"]
    assert edit(project, task["id"], reviewer="")["task"]["reviewer"] == ""


def test_editing_refuses_an_unknown_specialist_before_writing_anything(project: Path) -> None:
    task = card(project, reviewer=HUMAN)
    with pytest.raises(BadRequest):
        edit(project, task["id"], reviewer="taskops-collectrs")
    assert ask(project, task["id"])["task"]["reviewer"] == HUMAN


# ---- enforcement, from literals


def a_card(reviewer: str) -> Task:
    return Task(id="tk-aaaaaa", title="t", spec="s", status="review", priority=2, parent=None,
                labels=[], files=[], created_by="dev:berna", assignee="", reviewer=reviewer,
                created=CLOCK, updated=CLOCK)


def closing_facts(reviewer: str, **over: object) -> Facts:
    base: dict[str, object] = {"task": a_card(reviewer), "actor": "agent:berna/one",
                               "has_live_lease": True, "commits": 1, "open_children": 0,
                               "no_code": False, "justification": "", "unpushed": 0,
                               "reviewer": reviewer}
    return Facts(**{**base, **over})           # type: ignore[arg-type]


def refusal(reviewer: str, **over: object) -> str:
    """The guard's answer to `→ done`, as text. "" means it allowed the close."""
    try:
        check_move(closing_facts(reviewer, **over), "done")
    except GuardFailed as refused:
        return str(refused)
    return ""


def test_a_card_reviewed_by_a_person_refuses_every_agent_and_says_who() -> None:
    """The half that makes it policy: not "you reviewed your own work" — nobody automated
    may close this at all, and the sentence names who is waited on."""
    assert "dev:ana" in refusal("dev:ana")
    assert "human" in refusal(HUMAN)


def test_the_person_it_names_may_close_it() -> None:
    assert refusal(HUMAN, actor="dev:berna") == ""


def test_a_second_agent_may_not_stand_in_for_the_person() -> None:
    """The old handoff rule would have let this through: a different agent closing a card a
    human was meant to read passes "you did not review your own work" and defeats the point."""
    assert refusal("dev:ana", actor="agent:berna/two", entered_review_by="agent:berna/one")


def test_an_agent_reviewer_keeps_todays_rule() -> None:
    """Named specialist: anyone but the agent that asked for the review."""
    assert refusal("taskops-verifier", actor="agent:berna/two",
                   entered_review_by="agent:berna/one") == ""
    assert "another's to close" in refusal("taskops-verifier", actor="agent:berna/one",
                                           entered_review_by="agent:berna/one")


def test_a_card_with_no_reviewer_and_no_criteria_closes_exactly_as_before() -> None:
    """THE regression guard. Every card written before this feature says "", and none of
    them may have gained a rule."""
    assert refusal("") == ""
    assert refusal("", actor="agent:berna/two", entered_review_by="agent:berna/one") == ""
    assert "another's to close" in refusal("", entered_review_by="agent:berna/one")


def test_the_reviewer_is_shown_where_the_card_is_read(project: Path) -> None:
    task = card(project, reviewer=HUMAN)
    assert "reviewer human" in render_view(ask(project, task["id"]))


def test_a_card_can_say_nobody_against_a_project_default(project: Path) -> None:
    """The case this exists for: a project decides `reviewer: human`, and a text fix has to be
    able to opt out. Before, an empty reviewer was indistinguishable from an omitted one, so
    the default won and every card — however trivial — waited for a person."""
    from taskops.storage import Store
    from taskops.usecases import context_state, plan

    context_state(project, "decision", "reviewer: human", actor="dev:ana")

    absent = plan(project, [{"title": "a", "spec": "s"}], actor="dev:ana")["created"][0]
    stated = plan(project, [{"title": "b", "spec": "s", "reviewer": "none"}],
                  actor="dev:ana")["created"][0]
    empty = plan(project, [{"title": "c", "spec": "s", "reviewer": ""}],
                 actor="dev:ana")["created"][0]

    with Store(project) as store:
        assert store.tasks.need(absent["id"])["reviewer"] == "human", "absent takes the default"
        assert store.tasks.need(stated["id"])["reviewer"] == "", "`none` means nobody"
        assert store.tasks.need(empty["id"])["reviewer"] == "", "stated-empty means nobody too"


def test_a_flag_nobody_passed_is_not_a_statement() -> None:
    """argparse hands an unset flag over as None, and reading that as "explicitly nothing"
    would make every card created from the CLI opt out of the project's decision silently."""
    from taskops.usecases._entry import stated as said

    assert said({"title": "x"}, "reviewer") is None
    assert said({"title": "x", "reviewer": None}, "reviewer") is None
    assert said({"title": "x", "reviewer": ""}, "reviewer") == ""
    assert said({"title": "x", "reviewer": "human"}, "reviewer") == "human"


def test_a_decision_keeps_its_reason_and_still_names_a_reviewer(tmp_path: Path) -> None:
    """The feature disabled itself the first time somebody used it properly. This project asks
    every decision to carry its why, so a real one reads `reviewer: peer — nobody closes work
    produced by their own agents` — the whole tail was read as a NAME, nothing matched, and the
    degradation to "" made every card come out with no reviewer. Silent, and indistinguishable
    from never having stated it."""
    init(tmp_path, install_git_hooks=False)
    state(tmp_path, "decision",
                  "reviewer: peer — nobody closes work produced by their own agents")

    made = plan(tmp_path, [{"title": "t", "spec": "s"}], actor="dev:berna")["created"][0]

    assert made["reviewer"] == "peer"
