"""The specialist registry: the parser, the override, the router, the fence, the copy.

Every assertion here is about a way the feature could be WRONG rather than absent — a parser
that guesses, an override that does not, a router that picks differently on two runs, a fence
that catches a human, and a materialiser that eats a file somebody wrote by hand.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskops import BadRequest
from taskops.transports.hooks._materialise import TARGET_DIR, materialise_agents
from taskops.usecases import init, next_task, plan
from taskops.usecases._agentfile import parse_agent
from taskops.usecases.agents import (
    MARKER,
    agent_for,
    agent_named,
    fenced,
    materialised,
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
    folder = root / ".taskops" / "agents"
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
    assert names == ["taskops-collectors"]


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


def test_a_project_with_no_registry_routes_to_nothing(project: Path) -> None:
    """THE regression guard: no `.taskops/agents/`, no behaviour change anywhere."""
    assert specialists(project) == []
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


# ---- materialisation


def test_the_copy_carries_the_marker_and_drops_our_keys(project: Path) -> None:
    """`labels` and `files` are taskops-only; a frontmatter key Claude Code does not know is
    noise in somebody else's file format."""
    write_agent(project, "taskops-collectors", COLLECTORS)
    materialise_agents(str(project))

    written = (project / TARGET_DIR / "taskops-collectors.md").read_text(encoding="utf-8")
    assert MARKER in written
    assert "labels:" not in written and "files:" not in written
    assert "model: sonnet" in written, "keys we do not own must survive untouched"
    assert "You own the ingestion path." in written


def test_a_hand_written_agent_is_never_touched(project: Path) -> None:
    """A coordination tool that eats a developer's files gets uninstalled the same afternoon."""
    folder = project / TARGET_DIR
    folder.mkdir(parents=True)
    mine = folder / "my-own.md"
    mine.write_text("---\nname: my-own\ndescription: mine\n---\n\nhands off\n", encoding="utf-8")
    clash = folder / "taskops-collectors.md"
    clash.write_text("---\nname: taskops-collectors\ndescription: mine too\n---\n\nkeep\n",
                     encoding="utf-8")
    write_agent(project, "taskops-collectors", COLLECTORS)

    materialise_agents(str(project))
    assert mine.exists(), "an unmarked file was pruned"
    assert "keep" in clash.read_text(encoding="utf-8"), "an unmarked file was overwritten"


def test_a_deleted_agent_stops_being_offered(project: Path) -> None:
    """A rename would otherwise leave the old specialist invokable forever."""
    path = write_agent(project, "taskops-collectors", COLLECTORS)
    materialise_agents(str(project))
    copied = project / TARGET_DIR / "taskops-collectors.md"
    assert copied.exists()

    path.unlink()
    materialise_agents(str(project))
    assert not copied.exists()


def test_materialising_twice_changes_nothing(project: Path) -> None:
    write_agent(project, "taskops-collectors", COLLECTORS)
    materialise_agents(str(project))
    copied = project / TARGET_DIR / "taskops-collectors.md"
    once = copied.read_text(encoding="utf-8")
    materialise_agents(str(project))
    assert copied.read_text(encoding="utf-8") == once


def test_the_copy_is_a_valid_agent_file(project: Path) -> None:
    """It has to parse as one, or the marker line broke the frontmatter it was inserted after."""
    spec = parse_agent(materialised(parse_agent(COLLECTORS, project / "c.md")), project / "c.md")
    assert spec["name"] == "taskops-collectors"
    assert spec["labels"] == []


def test_materialising_outside_a_project_is_silent(tmp_path: Path) -> None:
    """The hook contract: never speak, never block, never raise."""
    materialise_agents(str(tmp_path))


def test_materialising_stays_inside_the_hook_budget(project: Path) -> None:
    """It runs on the session's critical path, next to the sweep launch. A hook the session
    waits on is a hook that has to be over before anybody notices it started."""
    import time

    for i in range(10):
        write_agent(project, f"a{i}", COLLECTORS.replace("taskops-collectors", f"a{i}"))
    started = time.perf_counter()
    materialise_agents(str(project))
    assert (time.perf_counter() - started) < 0.1


def test_an_assignment_to_the_specialist_beats_its_own_fence(project: Path) -> None:
    """Labels are the routing HEURISTIC; an assignment is a DECISION. Found live: a card
    captured with `assign="agent:t/collector"` and no labels was then unclaimable by the very
    specialist it was assigned to — the fence read "outside your labels" on a card somebody
    had named it for on purpose."""
    from taskops.usecases import capture

    write_agent(project, "collector",
                "---\nname: collector\ndescription: d\nlabels: [collectors]\n---\nbody\n")
    made = capture(project, "look at the lake schemas", assign="agent:ana/collector",
                   actor="dev:ana")
    got = next_task(project, task=made["task"]["id"], actor="agent:ana/collector")
    assert got["claim"] is not None, got.get("reason")
