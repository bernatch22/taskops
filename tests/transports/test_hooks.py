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
from taskops.transports.hooks import _door
from taskops.transports.hooks import events as _events
from taskops.usecases import init, next_task, plan
from taskops.usecases.milestone import open_chapter


@pytest.fixture
def project(tmp_path: Path) -> Path:
    # Every card belongs to a chapter: the fixture opens one so the test can be about its own
    # subject rather than about that.
    init(tmp_path, install_git_hooks=False)
    open_chapter(tmp_path, "the chapter these tests plan into",
                 actor="dev:berna")
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


def test_session_start_states_the_role_even_on_an_empty_board(project: Path) -> None:
    """This replaces a test that pinned SILENCE on an empty project, and the replacement is
    the point rather than an accommodation.

    The old rule was "a session told you hold nothing has paid tokens to learn nothing", and
    it was right about the STATE and wrong about the ROLE. An empty board is exactly when the
    main session is about to be handed work and decide to do it itself — which is what two
    real sessions did, because the injection they read ended with "Run taskops_next to claim
    one". The role is the one thing worth saying to a session that holds nothing.
    """
    said = _events.session_start(event(project))["hookSpecificOutput"]["additionalContext"]

    assert "ORCHESTRATOR" in said
    assert "taskops_next" not in said, "the opening must never tell the main session to claim"


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


def test_session_start_leads_with_the_role_then_the_project_then_the_board(
        project: Path) -> None:
    """The ORDER is the argument. A session told the state before the role does the state
    itself; told the role first, it reads the same state as something to delegate."""
    from taskops.usecases import context_state

    context_state(project, "decision", "no runtime dependencies outside the stdlib")
    plan(project, [{"title": "Something ready", "spec": "x"}])

    said = _events.session_start(event(project))["hookSpecificOutput"]["additionalContext"]

    assert said.index("ORCHESTRATOR") < said.index("no runtime dependencies") \
        < said.index("Waiting on a decision")


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


def test_a_stop_with_a_half_done_card_blocks_naming_both_exits(root: Path) -> None:
    """The net, through the real handler. The reason IS the fix: both exits, per card, with
    the actor spelled out — a block that only says no teaches an agent to argue with the door."""
    from taskops.transports.hooks.claude import HANDLERS
    from taskops.usecases import next_task, plan

    task = plan(root, [{"title": "t", "spec": "s"}], actor="dev:ana")["created"][0]["id"]
    next_task(root, task=task, actor="agent:ana/api1", session="s-1")

    answer = HANDLERS["subagent-stop"]({"cwd": str(root), "session_id": "s-1",
                                        "agent_type": "api"})
    assert answer["decision"] == "block"
    assert "status=review" in answer["reason"] and "status=ready" in answer["reason"]
    assert "actor=agent:ana/api1" in answer["reason"]


def test_a_clean_stop_passes_and_still_posts_the_standup(root: Path) -> None:
    from taskops.transports.hooks.claude import HANDLERS

    assert HANDLERS["stop"]({"cwd": str(root), "session_id": "s-1"}) == {}


def test_a_broken_board_never_traps_a_session(tmp_path: Path) -> None:
    """Fail OPEN: a taskops bug may never hold somebody's session at the door. A directory
    that is not even a project is the cheapest stand-in for every internal failure."""
    from taskops.transports.hooks.claude import HANDLERS

    assert HANDLERS["subagent-stop"]({"cwd": str(tmp_path), "session_id": "s-1"}) == {}


# ---- the review that nobody picked up


def _handover(project: Path, monkeypatch: Any, *, reviewer: str = "") -> str:
    """One card taken to `review` by a worker — the exact state two live sessions died in."""
    from taskops.usecases import update

    monkeypatch.setenv("TASKOPS_ACTOR", "agent:berna/w1")
    card = plan(project, [{"title": "The parser", "spec": "x", "reviewer": reviewer,
                           "acceptance": ["WHEN x THE SYSTEM SHALL y"]}])["created"][0]["id"]
    next_task(project, task=card, actor="agent:berna/w1", session="sess-1")
    update(project, card, status="review", actor="agent:berna/w1", comment="criterion met")
    return card


def test_a_worker_stopping_is_told_nothing_it_cannot_do(project: Path,
                                                        monkeypatch: Any) -> None:
    """This REPLACES a test that pinned the opposite, and the replacement is the whole lesson.

    `SubagentStop` injects into the context of the SUB-AGENT that just stopped — a worker,
    whose tools are taskops plus Read/Write/Edit/Bash. Spawning a sub-agent is the
    orchestrator's capability alone. The old message asked the worker to spawn a verifier: it
    could not, said so, was asked again, and spent four turns explaining to nobody that it
    lacks the tool. An instruction delivered to somebody who cannot act on it is worse than
    silence — it costs turns and teaches the reader that this channel talks nonsense.
    """
    _handover(project, monkeypatch)

    said = _door.subagent_stop(event(project))

    assert said == {}, "a worker that owes nothing leaves quietly"


def test_the_orchestrator_is_the_one_asked_for_the_verifier(project: Path,
                                                            monkeypatch: Any) -> None:
    """The ask belongs to `Stop`, which fires for the MAIN conversation — the one reader that
    can actually spawn."""
    card = _handover(project, monkeypatch)

    verdict = _events.stop(event(project))

    assert verdict["decision"] == "block"
    assert card in verdict["reason"] and "taskops-verifier" in verdict["reason"]


def test_a_turn_cannot_end_on_a_review_this_session_opened(project: Path,
                                                           monkeypatch: Any) -> None:
    """Stop holds the door for the case the session CAUSED: work it finished and left
    unverified. A card in review reads as active on the board for as long as nobody looks."""
    card = _handover(project, monkeypatch)

    verdict = _events.stop(event(project))

    assert verdict["decision"] == "block"
    assert card in verdict["reason"]


def test_stop_never_blocks_over_work_nobody_started(project: Path, monkeypatch: Any) -> None:
    """The scope, and it is deliberate. Blocking on everything `attention` reports would trap
    somebody who asked a question into doing a board's worth of work first — a ready card is
    not this turn's debt, and a turn that cannot end is a worse failure than a stale board."""
    monkeypatch.setenv("TASKOPS_ACTOR", "dev:berna")
    plan(project, [{"title": "Nobody has touched this", "spec": "x"}])

    assert _events.stop(event(project)) == {}


def test_a_session_is_let_go_after_being_told_twice(project: Path, monkeypatch: Any) -> None:
    """The same limit `unfinished` uses, for the same reason: an agent that has read the
    message twice will not act on a third copy."""
    _handover(project, monkeypatch)

    assert _events.stop(event(project))["decision"] == "block"
    assert _events.stop(event(project))["decision"] == "block"
    assert _events.stop(event(project)) == {}, "told twice, then let go"



def test_the_hook_never_tells_a_session_to_spawn_a_policy() -> None:
    r"""It did: `spawn a \`peer\` sub-agent for it`. There is no such agent — `peer` and `human`
    are POLICIES about who may close a card, and only a registered specialist is a name you can
    spawn. A live session read that line, ignored it, and spawned the right thing anyway, which
    is luck. Five separate failures this session have been an instruction naming something that
    does not exist, and every previous one cost a run."""
    from taskops.usecases.pending import verify_text

    rows = [{"task": {"id": "tk-1", "title": "t", "reviewer": "peer"}},
            {"task": {"id": "tk-2", "title": "t", "reviewer": "human"}},
            {"task": {"id": "tk-3", "title": "t", "reviewer": ""}},
            {"task": {"id": "tk-4", "title": "t", "reviewer": "db-migrator"}}]

    said = verify_text(rows, closing=False)

    assert "`peer` sub-agent" not in said and "`human` sub-agent" not in said
    assert said.count("`taskops-verifier`") == 3, "policies and blank fall to the verifier"
    assert "`db-migrator`" in said, "a real registered specialist is still named"


def test_a_peer_review_does_not_nag_the_author_s_own_session(project: Path,
                                                             monkeypatch: Any) -> None:
    """With `reviewer: peer` the author's session gets NO reminder, and that silence is the
    fix working: the review belongs to the other developer, and telling this session to spawn
    a verifier would tell it to spawn one the close guard is going to refuse."""
    _handover(project, monkeypatch, reviewer="peer")

    assert _door.subagent_stop(event(project)) == {}


def test_session_start_speaks_to_BOTH_audiences(project: Path) -> None:
    """Two channels, and only one of them is the model's.

    `additionalContext` is wrapped in a system reminder the person never sees, and plain stdout
    from a SessionStart hook is hidden from them too. `systemMessage` is the only field that
    reaches the terminal — so without it a session opened, the agent silently received the whole
    board, and the human watching could not tell taskops had run, let alone that three cards
    were waiting on them.

    Asserted HERE and not only on the renderer: a line that is right and not wired is a line
    nobody sees, and the renderer's own tests pass either way.
    """
    from taskops.usecases import plan

    plan(project, [{"title": "one", "spec": "s"}], actor="dev:ana")
    response = _events.session_start(event(project))

    import re

    said = response["systemMessage"]
    assert response["hookSpecificOutput"]["additionalContext"], "the model still gets the board"
    assert re.sub(r"\x1b\[[0-9;]*m", "", said).startswith("taskops is tracking this project"), (
        "and the person gets a sentence that names what is running, not a count")
    assert "\n" not in said, (
        "ONE line: a four-section block arrived as a run-on paragraph on a real screen, so the "
        "renderer never emits a newline rather than relying on what the harness does with one")
