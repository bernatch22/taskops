"""The specialist registry: the parser, the override, the router, the fence, the copy.

Every assertion here is about a way the feature could be WRONG rather than absent — a parser
that guesses, an override that does not, a router that picks differently on two runs, a fence
that catches a human, and a registry that is Claude Code's own rather than a copy of it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskops import BadRequest
from taskops.usecases import init, next_task, plan
from taskops.usecases._agentfile import parse_agent
from taskops.usecases.agents import (
    REGISTRY_DIR,
    agent_for,
    agent_named,
    fenced,
    registry,
    specialists,
)

COLLECTORS = """---
name: taskops-collectors
description: The collectors specialist.
tools: [Read, Edit]
model: sonnet
labels: [collectors, etl]
files: ["src/data/**"]
---

# The collectors specialist

You own the ingestion path.
"""


def write_agent(root: Path, name: str, text: str) -> Path:
    folder = root / REGISTRY_DIR
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.md"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def project(tmp_path: Path) -> Path:
    init(tmp_path, install_git_hooks=False)
    return tmp_path


# ---- the parser


def test_the_subset_round_trips(tmp_path: Path) -> None:
    """Scalars and inline lists, which is everything a real agent file uses."""
    spec = parse_agent(COLLECTORS, tmp_path / "taskops-collectors.md")
    assert spec["name"] == "taskops-collectors"
    assert spec["description"] == "The collectors specialist."
    assert spec["labels"] == ["collectors", "etl"]
    assert spec["files"] == ["src/data/**"]
    assert spec["text"] == COLLECTORS


def test_yaml_we_do_not_parse_is_refused_by_name(tmp_path: Path) -> None:
    """A partial YAML parser that GUESSES turns a typo into a silently wrong registry, and the
    agent then routes cards nobody meant it to have. The refusal has to name the file, because
    the reader is looking at a session that started fine and one agent that is missing."""
    fancy = "---\nname: x\nlabels:\n  - collectors\n---\n\nbody\n"
    with pytest.raises(BadRequest) as caught:
        parse_agent(fancy, tmp_path / "x.md")
    assert "x.md" in str(caught.value)
    assert "key: value" in str(caught.value)


def test_a_file_with_no_name_is_refused(tmp_path: Path) -> None:
    with pytest.raises(BadRequest, match="name"):
        parse_agent("---\ndescription: nothing\n---\n\nbody\n", tmp_path / "y.md")


def test_a_malformed_file_warns_and_is_skipped_not_raised(project: Path) -> None:
    """A typo in one agent file may never stop a session from starting — these are edited by
    hand, and the blast radius of a bad one has to be that one agent."""
    write_agent(project, "good", COLLECTORS)
    write_agent(project, "bad", "not frontmatter at all\n")
    with pytest.warns(UserWarning, match="bad.md"):
        names = [a["name"] for a in specialists(project)]
    assert "taskops-collectors" in names
    assert "bad" not in names


# ---- the two directories, one registry


def test_the_plugin_defaults_are_in_the_registry(project: Path) -> None:
    assert "taskops-worker" in [a["name"] for a in registry(project)]


def test_a_repo_file_overrides_the_plugin_default_of_the_same_name(project: Path) -> None:
    """A project must be able to replace the stock worker without forking the plugin."""
    write_agent(project, "taskops-worker",
                "---\nname: taskops-worker\ndescription: ours\nlabels: [ui]\n---\n\nmine\n")
    found = {a["name"]: a for a in registry(project)}
    assert found["taskops-worker"]["description"] == "ours"
    assert found["taskops-worker"]["labels"] == ["ui"]


# ---- routing


def test_the_most_specific_match_wins(project: Path) -> None:
    write_agent(project, "one", "---\nname: one\ndescription: d\nlabels: [etl]\n---\n\nb\n")
    write_agent(project, "two",
                "---\nname: two\ndescription: d\nlabels: [etl, collectors]\n---\n\nb\n")
    assert agent_for(project, ["etl", "collectors"]) == "two"


def test_a_tie_breaks_alphabetically_and_stays_there(project: Path) -> None:
    """Deterministic on purpose: a router that picked differently on two runs makes a fleet
    unreproducible, and "which agent got this card" is the first question when one goes wrong."""
    write_agent(project, "zeta", "---\nname: zeta\ndescription: d\nlabels: [etl]\n---\n\nb\n")
    write_agent(project, "alpha", "---\nname: alpha\ndescription: d\nlabels: [etl]\n---\n\nb\n")
    assert {agent_for(project, ["etl"]) for _ in range(5)} == {"alpha"}


def test_no_match_routes_to_nothing(project: Path) -> None:
    write_agent(project, "one", "---\nname: one\ndescription: d\nlabels: [etl]\n---\n\nb\n")
    assert agent_for(project, ["ui"]) == ""


def test_the_stock_specialists_route_nothing_by_label(project: Path) -> None:
    """`init` writes our specialists into every project, so "no registry" no longer exists —
    this pins what replaced it: none of the stock ones carries labels, so label routing still
    resolves to nothing until a project defines its own.

    The SET is asserted, not a count: each of these is a role the engine or a hook names by
    hand somewhere, so one appearing or disappearing is a thing to notice rather than a number
    to update.
    """
    assert {a["name"] for a in specialists(project)} == {
        "taskops-verifier", "taskops-worker", "taskops-fixer", "taskops-lead"}
    assert agent_for(project, ["etl"]) == ""


# ---- the fence at the claim


def test_a_specialist_is_refused_a_card_outside_its_labels(project: Path) -> None:
    write_agent(project, "taskops-collectors", COLLECTORS)
    made = plan(project, [{"title": "restyle the header", "spec": "x", "labels": ["ui"]}],
                actor="dev:berna")["created"][0]

    refused = next_task(project, actor="agent:berna/taskops-collectors", task=made["id"])
    assert refused["claim"] is None
    assert "collectors" in refused["reason"] and "ui" in refused["reason"], (
        "the refusal must name BOTH label sets — 'no' is not an answer, 'you do X, this is Y' is")


def test_the_specialist_still_gets_its_own_cards(project: Path) -> None:
    write_agent(project, "taskops-collectors", COLLECTORS)
    made = plan(project, [{"title": "fix the loader", "spec": "x", "labels": ["etl"]}],
                actor="dev:berna")["created"][0]

    mine = next_task(project, actor="agent:berna/taskops-collectors", task=made["id"])
    assert mine["claim"] is not None
    assert mine["claim"]["view"]["task"]["id"] == made["id"]


def test_the_pool_hides_what_the_specialist_may_not_have(project: Path) -> None:
    write_agent(project, "taskops-collectors", COLLECTORS)
    plan(project, [{"title": "restyle", "spec": "x", "labels": ["ui"]}], actor="dev:berna")
    assert next_task(project, actor="agent:berna/taskops-collectors")["claim"] is None


def test_an_unknown_actor_is_not_fenced(project: Path) -> None:
    """A human's ad-hoc worker must not become fenced in just because specialists exist."""
    write_agent(project, "taskops-collectors", COLLECTORS)
    made = plan(project, [{"title": "restyle", "spec": "x", "labels": ["ui"]}],
                actor="dev:berna")["created"][0]
    assert next_task(project, actor="agent:berna/w1", task=made["id"])["claim"] is not None


def test_an_agent_with_no_labels_fences_nobody(project: Path) -> None:
    assert fenced(agent_named(project, "agent:berna/taskops-worker"), ["ui"]) == ""


# ---- the registry IS Claude Code's


def test_the_registry_is_claude_codes_own_directory() -> None:
    """The whole simplification in one assertion. A parallel `.taskops/agents/` needed a
    copier, a marker, a pruner and a name translator, and every one of those was a bug
    waiting: Claude Code's project subagents are already committed, already shared with the
    team, and already the only thing the host can spawn."""
    assert REGISTRY_DIR == ".claude/agents"


def test_our_keys_ride_in_the_same_frontmatter(project: Path) -> None:
    """One file, two readers. Claude Code ignores frontmatter it does not recognise, so
    `labels` and `files` sit beside `name` and `tools` instead of in a second document that
    could disagree with the first."""
    write_agent(project, "api",
                "---\nname: api\ndescription: d\ntools: [Read]\n"
                "labels: [api, backend]\nfiles: [\"src/api/**\"]\n---\nbody\n")
    spec = specialists(project)[0]
    assert spec["labels"] == ["api", "backend"]
    assert spec["files"] == ["src/api/**"]


def test_an_agent_written_for_claude_code_alone_is_still_read(project: Path) -> None:
    """No labels is not an error — it is every subagent anybody already has. It routes to
    nothing and fences nobody, which is exactly the behaviour a project that never heard of
    taskops should get."""
    write_agent(project, "plain", "---\nname: plain\ndescription: d\n---\nbody\n")
    spec = next(a for a in specialists(project) if a["name"] == "plain")
    assert spec["labels"] == []


def test_an_orchestrator_is_refused_a_card_rather_than_asked_not_to_take_one(
        project: Path) -> None:
    """Told in three separate places not to implement the work itself, a session did exactly
    that — twice. An instruction is what a model weighs against everything else in its context;
    a refusal is not. `claims: false` is the difference."""
    write_agent(project, "boss",
                "---\nname: boss\ndescription: plans\nclaims: false\n---\nbody\n")
    boss = agent_named(project, "agent:ana/boss")
    assert boss is not None and boss["claims"] is False
    refusal = fenced(boss, ["anything"])
    assert "does not hold cards" in refusal
    assert "Dispatch" in refusal, "the refusal must name what to do instead"


def test_every_other_agent_still_claims(project: Path) -> None:
    """Absent means yes. A registry written before this key existed, and every ordinary
    specialist, must keep working unchanged — this is the regression guard."""
    write_agent(project, "api", "---\nname: api\ndescription: d\nlabels: [api]\n---\nbody\n")
    api = agent_named(project, "agent:ana/api")
    assert api is not None and api["claims"] is True
    assert fenced(api, ["api"]) == ""


