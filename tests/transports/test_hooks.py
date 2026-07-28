"""The Claude Code hook protocol — the shapes the harness reads back.

These are pinned tightly because every one of them is an EXTERNAL contract: a field name
typoed here does not fail, it silently does nothing. A `permissionDecision` the harness does
not recognise means a commit that should have been denied goes through, and nothing anywhere
says so.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from taskops.engine import commitline
from taskops.transports.hooks import events as _events
from taskops.usecases import init, next_task, plan


@pytest.fixture
def project(tmp_path: Path) -> Path:
    init(tmp_path, install_git_hooks=False)
    return tmp_path


def event(cwd: Path, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"session_id": "sess-1", "cwd": str(cwd),
                            "hook_event_name": "PreToolUse", "tool_name": "Bash",
                            "tool_input": {}}
    return {**base, **over}


# ---- the commit line parser


@pytest.mark.parametrize("command,expected", [
    ("git commit -m 'hi'", True),
    ("git commit", True),
    ("git -C /tmp/x commit -m 'hi'", True),
    ("git log --grep commit", False),
    ("git status", False),
    ("echo git commit", False),
    ("", False),
])
def test_recognising_a_commit(command: str, expected: bool) -> None:
    """`git log --grep commit` is the case that matters: a naive substring check would treat
    it as a commit and guard a read-only command."""
    assert commitline.is_commit(command) is expected


def test_reading_the_message() -> None:
    assert commitline.message_of('git commit -m "fix the parser"') == "fix the parser"
    assert commitline.message_of("git commit --message 'x'") == "x"


def test_no_single_message_reads_as_none() -> None:
    """An editor commit, a `-F` file, or several `-m` paragraphs. The caller can do nothing
    useful with any of them beyond declining to rewrite, so they collapse to ""."""
    assert commitline.message_of("git commit") == ""
    assert commitline.message_of("git commit -F msg.txt") == ""
    assert commitline.message_of("git commit -m one -m two") == ""


def test_rewriting_preserves_the_rest_of_the_command() -> None:
    out = commitline.with_message("git commit --no-verify -m 'old' -a", "new")
    assert "--no-verify" in out and "-a" in out
    assert commitline.message_of(out) == "new"


def test_a_compound_command_is_never_rewritten() -> None:
    """THE dangerous case. `git commit -m x && git push` rewritten by something that does not
    understand shell operators would drop the push — the agent's work silently not shipping is
    far worse than a missing trailer."""
    assert commitline.with_message("git commit -m 'x' && git push", "y") == ""
    assert commitline.with_message("git commit -m \"$(date)\"", "y") == ""


def test_an_unbalanced_quote_does_not_raise() -> None:
    """The input is whatever an agent typed. A lexing failure must read as "cannot analyse"
    rather than take the hook down and block the commit."""
    assert commitline.is_commit("git commit -m 'unclosed") is False
    assert commitline.message_of("git commit -m 'unclosed") == ""


# ---- PreToolUse


def test_a_non_commit_command_gets_no_response(project: Path) -> None:
    """This hook fires on EVERY Bash call, so the common path must be silent and free."""
    assert _events.pre_tool_use(event(project, tool_input={"command": "ls -la"})) == {}


def test_a_commit_without_a_claim_is_denied_with_the_exact_field_names(project: Path) -> None:
    """The external contract, pinned field by field. A typo here fails OPEN and silently."""
    plan(project, [{"title": "T", "spec": "x"}])
    response = _events.pre_tool_use(
        event(project, tool_input={"command": "git commit -m 'nope'"}))
    output = response["hookSpecificOutput"]
    assert output["hookEventName"] == "PreToolUse"
    assert output["permissionDecision"] == "deny"
    assert "taskops:" in output["permissionDecisionReason"]


def test_the_response_is_json_serialisable(project: Path) -> None:
    """It goes out through `json.dumps` on stdout, so a non-serialisable value would make the
    hook print a traceback where the harness expects an object."""
    plan(project, [{"title": "T", "spec": "x"}])
    response = _events.pre_tool_use(
        event(project, tool_input={"command": "git commit -m 'x'"}))
    assert json.loads(json.dumps(response)) == response


# ---- SessionStart and PostToolUse


def test_session_start_is_silent_on_an_empty_project(project: Path) -> None:
    """A session told "you hold nothing" has paid tokens to learn nothing."""
    assert _events.session_start(event(project)) == {}


def test_session_start_injects_what_the_session_holds(project: Path,
                                                     monkeypatch: Any) -> None:
    """A hook has no argument for identity: it reads `$TASKOPS_ACTOR`, which is what the plugin
    exports per session. Setting it here is not test scaffolding — it IS the mechanism."""
    monkeypatch.setenv("TASKOPS_ACTOR", "agent:berna/one")
    planned = plan(project, [{"title": "Held work", "spec": "x"}])
    next_task(project, actor="agent:berna/one", session="sess-1")
    response = _events.session_start(event(project))
    output = response["hookSpecificOutput"]
    assert output["hookEventName"] == "SessionStart"
    assert planned["created"][0]["id"] in output["additionalContext"]


def test_post_tool_use_delivers_a_message_from_another_agent(project: Path,
                                                             monkeypatch: Any) -> None:
    """The whole agent-to-agent claim, at the point of delivery: a message written by one agent
    reaches another on its very next tool call."""
    from taskops.usecases import update

    monkeypatch.setenv("TASKOPS_ACTOR", "agent:berna/one")
    planned = plan(project, [{"title": "Shared", "spec": "x"}])
    next_task(project, actor="agent:berna/one")
    update(project, planned["created"][0]["id"], actor="agent:ana/two",
           comment="Careful, I am in that file.", mentions=("agent:berna/one",))

    response = _events.post_tool_use(
        event(project, tool_name="Edit", tool_input={"file_path": "a.py"}))
    assert "Careful, I am in that file." in \
        response["hookSpecificOutput"]["additionalContext"]


def test_post_tool_use_is_silent_with_no_messages(project: Path,
                                                  monkeypatch: Any) -> None:
    """It runs after every tool call. Speaking each time would inject noise hundreds of
    times into one session."""
    monkeypatch.setenv("TASKOPS_ACTOR", "agent:berna/one")
    plan(project, [{"title": "T", "spec": "x"}])
    next_task(project, actor="agent:berna/one")
    assert _events.post_tool_use(event(project, tool_name="Read")) == {}


# ---- the sweep launch on session start


@pytest.fixture
def spawned(monkeypatch: Any) -> list[list[str]]:
    """Every spawn, captured. A REAL sweep calls the model, so no test here may reach one —
    what is under test is the command and the guards, never the report."""
    calls: list[list[str]] = []
    monkeypatch.setattr("taskops.transports.hooks._sweeplaunch._spawn", calls.append)
    return calls


def with_events(project: Path) -> Path:
    plan(project, [{"title": "T", "spec": "x"}])
    return project


def test_session_start_launches_the_sweep_detached(project: Path,
                                                   spawned: list[list[str]]) -> None:
    """The zero-setup trigger: opening a session is what gets yesterday written up."""
    from taskops.transports.hooks.claude import session_start

    session_start(event(with_events(project)))
    assert len(spawned) == 1
    assert spawned[0][1:] == ["-m", "taskops.transports.cli.main",
                              "report", "sweep", "--repo", str(project)]


def test_the_second_session_of_the_day_does_not_sweep_again(project: Path,
                                                            spawned: list[list[str]]) -> None:
    """Resuming ten sessions in a morning must be ONE model call, not ten."""
    from taskops.transports.hooks.claude import session_start

    with_events(project)
    for _ in range(5):
        session_start(event(project))
    assert len(spawned) == 1


def test_no_sweep_env_var_turns_it_off(project: Path, spawned: list[list[str]],
                                       monkeypatch: Any) -> None:
    from taskops.transports.hooks.claude import session_start

    monkeypatch.setenv("TASKOPS_NO_SWEEP", "1")
    session_start(event(with_events(project)))
    assert spawned == []


def test_an_empty_project_with_no_remote_never_spawns(project: Path,
                                                      spawned: list[list[str]]) -> None:
    """Nothing to narrate and nowhere to send it. The cheap answer must be reached without
    paying for a process."""
    from taskops.transports.hooks.claude import session_start

    session_start(event(project))
    assert spawned == []


def test_the_launch_is_silent_when_the_spawn_itself_fails(project: Path,
                                                          monkeypatch: Any) -> None:
    """A broken sweep may never stop a session from starting."""
    from taskops.transports.hooks._sweeplaunch import launch_sweep

    def boom(_command: list[str]) -> None:
        raise OSError("no such interpreter")

    monkeypatch.setattr("taskops.transports.hooks._sweeplaunch._spawn", boom)
    launch_sweep(str(with_events(project)))


def test_the_launch_is_silent_outside_a_project(tmp_path: Path,
                                                spawned: list[list[str]]) -> None:
    from taskops.transports.hooks._sweeplaunch import launch_sweep

    launch_sweep(str(tmp_path))
    assert spawned == []


@pytest.mark.usefixtures("spawned")
def test_the_hook_returns_immediately(project: Path) -> None:
    """The hook is SYNCHRONOUS and the session waits on it. Measured, because "it detaches"
    is exactly the kind of claim that stays true until somebody adds one blocking call."""
    import time

    from taskops.transports.hooks._sweeplaunch import launch_sweep

    with_events(project)
    started = time.perf_counter()
    launch_sweep(str(project))
    assert (time.perf_counter() - started) < 0.1


# ---- the wire


def test_the_command_exits_zero_even_when_it_denies(project: Path, monkeypatch: Any) -> None:
    """A non-zero exit is ALSO read as a denial, so returning both would refuse the call twice
    — once without the reason attached, and that is the version the agent would see."""
    from taskops.transports.hooks.__main__ import main

    plan(project, [{"title": "T", "spec": "x"}])
    payload = json.dumps(event(project, tool_input={"command": "git commit -m 'x'"}))
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    assert main(["pre-tool-use"]) == 0


def test_a_broken_project_fails_open(tmp_path: Path, monkeypatch: Any) -> None:
    """No project at all. The hook must answer nothing rather than block the tool call.

    Fail-open is deliberate: a hook that raised would block the commit it was inspecting, and
    blocking a developer because taskops had a bad day is how this gets uninstalled.
    """
    from taskops.transports.hooks.__main__ import main

    payload = json.dumps(event(tmp_path, tool_input={"command": "git commit -m 'x'"}))
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    assert main(["pre-tool-use"]) == 0
