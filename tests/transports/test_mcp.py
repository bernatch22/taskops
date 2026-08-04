"""The MCP surface: the handshake, the generated schemas, and the dispatch table.

The schema tests are the important ones. Nothing type-checks a JSON Schema, so a generator
that quietly stopped emitting a parameter would leave the tool advertising a shape the
dispatch no longer reads — and the only symptom is an agent that keeps sending an argument
nobody uses, or a host rejecting a call that would have worked.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from taskops.transports.mcp import PROTOCOL, listing, respond, serve
from taskops.transports.mcp.dispatch import HANDLERS
from taskops.transports.mcp.tools import TOOLS
from taskops.usecases.milestone import open_chapter


def call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    reply = respond({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                     "params": {"name": name, "arguments": arguments}})
    return reply["result"] if reply else {}


def text_of(result: dict[str, Any]) -> str:
    return str(result["content"][0]["text"])


def test_initialize_returns_the_protocol_and_the_instructions() -> None:
    reply = respond({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert reply is not None
    result = reply["result"]
    assert result["protocolVersion"] == PROTOCOL
    assert result["serverInfo"]["name"] == "taskops"
    assert "taskops_next" in result["instructions"]


def test_a_notification_gets_no_reply() -> None:
    """Answering an id-less message is a protocol violation some hosts read as a broken
    server — and it returns before any work, so a notification cannot cost a database open."""
    assert respond({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_every_tool_has_a_handler_and_every_handler_a_tool() -> None:
    """The anti-drift check between the advertised surface and the dispatch table.

    A tool with no handler is one an agent will call and get "unknown tool" for; a handler
    with no tool is dead code nobody can reach.
    """
    assert {tool.name for tool in TOOLS} == set(HANDLERS)


@pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t.name)
def test_every_schema_declares_the_repository(tool: Any) -> None:
    schema = next(t["inputSchema"] for t in listing() if t["name"] == tool.name)
    assert "repo_path" in schema["properties"]
    assert schema["required"] == ["repo_path"] or "repo_path" in schema["required"]


@pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t.name)
def test_every_parameter_is_described(tool: Any) -> None:
    """A field with no description is a field an agent has to guess at, and it WILL guess."""
    schema = next(t["inputSchema"] for t in listing() if t["name"] == tool.name)
    undescribed = [name for name, spec in schema["properties"].items()
                   if not spec.get("description")]
    assert not undescribed, f"{tool.name}: {undescribed} have no description"


def test_a_literal_becomes_an_enum() -> None:
    """The allowed values ARE the documentation. Rendered as a bare string, an agent can send
    anything and only finds out at dispatch."""
    schema = next(t["inputSchema"] for t in listing() if t["name"] == "taskops_update")
    assert set(schema["properties"]["status"]["enum"]) >= {"done", "released", "blocked"}


def test_the_task_list_is_an_array() -> None:
    schema = next(t["inputSchema"] for t in listing() if t["name"] == "taskops_plan")
    assert schema["properties"]["tasks"]["type"] == "array"


def test_an_unknown_tool_names_the_real_ones() -> None:
    result = call("taskops_nonexistent", {"repo_path": "."})
    assert result["isError"] is True
    assert "taskops_next" in text_of(result)


def test_a_missing_repository_is_an_answer_not_a_crash(tmp_path: Path) -> None:
    """An uninitialised project is ordinary traffic on this surface, and the reply has to say
    what to run — an agent given a traceback has nothing to act on."""
    result = call("taskops_next", {"repo_path": str(tmp_path)})
    assert result["isError"] is True
    assert "taskops init" in text_of(result)


def test_a_missing_argument_is_an_answer_not_a_crash() -> None:
    result = call("taskops_update", {"repo_path": "."})
    assert result["isError"] is True
    assert "task" in text_of(result)


def test_the_stdio_loop_skips_garbage_and_keeps_going() -> None:
    """One malformed line must not lose the rest of the session, and there is no id to answer
    it with anyway."""
    lines = ["not json at all",
             json.dumps({"jsonrpc": "2.0", "id": 7, "method": "tools/list"}), ""]
    out = io.StringIO()
    serve(io.StringIO("\n".join(lines) + "\n"), out)
    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    assert len(replies) == 1
    assert replies[0]["id"] == 7
    assert len(replies[0]["result"]["tools"]) == len(TOOLS)


def test_the_whole_loop_over_the_wire(tmp_path: Path) -> None:
    """plan then next, as JSON-RPC, against a real project.

    The transport's own test: everything else here checks a shape, and this checks that a
    host talking to this server actually gets work out of it.
    """
    from taskops.usecases import init

    # Every card belongs to a chapter: the fixture opens one so the test can be about its own
    # subject rather than about that.
    init(tmp_path, install_git_hooks=False)
    open_chapter(tmp_path, "the chapter these tests plan into",
                 actor="dev:berna")
    planned = call("taskops_plan", {"repo_path": str(tmp_path),
                                    "tasks": [{"title": "Write the parser",
                                               "spec": "Full brief."}]})
    assert "isError" not in planned
    assert "planned 1 task" in text_of(planned)

    claimed = call("taskops_next", {"repo_path": str(tmp_path),
                                    "actor": "agent:berna/one"})
    assert "isError" not in claimed
    assert "git switch -c tk/" in text_of(claimed)


def test_a_stringly_typed_task_list_is_accepted(tmp_path: Path) -> None:
    """FIELD HABIT: a model sends `tasks` as a JSON STRING, learned from tools whose
    arguments are all strings. Rejecting it teaches the agent nothing about the real
    requirement."""
    from taskops.usecases import init

    init(tmp_path, install_git_hooks=False)
    open_chapter(tmp_path, "the chapter these tests plan into",
                 actor="dev:berna")
    result = call("taskops_plan", {"repo_path": str(tmp_path),
                                   "tasks": '[{"title": "From a string", "spec": "x"}]'})
    assert "isError" not in result
    assert "From a string" in text_of(result)


def test_the_mcp_surface_cannot_ask_taskops_to_spawn_a_process() -> None:
    """THE rule, pinned. A model calling a tool must not be able to make this package launch another
    Claude Code.

    The use case CAN spawn and `taskops run` does, because that is a human at a terminal
    asking for it. Over MCP the field is absent from the schema and unread by the handler, so an agent
    that sends it gets a prepared brief anyway.

    Why it matters: spawning opens a NEW billed session per worker, and an agent inside a session
    already has a way to run work in parallel — its own sub-agent tool, on the subscription that is
    already paid for. A real fleet of six drained an API balance this way and left six cards claimed by
    processes that no longer existed.
    """
    schema = next(t["inputSchema"] for t in listing() if t["name"] == "taskops_dispatch")
    assert "spawn" not in schema["properties"], "MCP is advertising a way to spawn processes"

    from taskops.transports.mcp import _reads, _writes

    for module in (_reads, _writes):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert '"spawn"' not in source, f"{module.__name__} reads `spawn` — it must never pass it"


def test_dispatch_over_mcp_returns_briefs_and_starts_nothing(tmp_path: Path) -> None:
    """The positive half: what an agent gets instead is a brief it can hand to a sub-agent."""
    from taskops.usecases import init, plan

    init(tmp_path, install_git_hooks=False)
    open_chapter(tmp_path, "the chapter these tests plan into",
                 actor="dev:berna")
    plan(tmp_path, [{"title": "Parallel work", "spec": "x"}], actor="dev:berna")

    result = call("taskops_dispatch", {"repo_path": str(tmp_path), "count": 1,
                                       "spawn": True, "actor": "dev:berna"})
    assert "isError" not in result
    text = text_of(result)
    assert "SPAWN THEM BELOW" in text, "an agent sending spawn=true got a process started"
    assert "YOUR WORKTREE" in text, "the brief is missing"


@pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t.name)
def test_no_description_tells_an_agent_to_pass_a_field_the_schema_lacks(tool: Any) -> None:
    """A backticked `name: value` in a description is an INSTRUCTION to pass a parameter. If the
    schema has no such field, the agent sends it and it is silently dropped.

    THIS TEST WAS WRITTEN BECAUSE IT HAPPENED, AND THEN REWRITTEN TWICE BECAUSE THE FIRST TWO VERSIONS
    WERE VACUOUS — which is worth recording, because a green invariant that cannot fail is worse than
    no invariant:

    1. The first regex looked for a backticked word followed by a colon OUTSIDE the backticks. The real
       text had the colon INSIDE them, so it matched nothing.
    2. The second filtered candidates to "names that are a field of SOME tool" — to avoid flagging
       `taskops recover` as an invented parameter. But `spawn` had been removed from EVERY tool, so it
       failed that filter and was dropped. The test passed against the exact bug it was written for.

    The rule that works is narrower and needs no allowlist: only the `name: value` / `name=value` form
    counts, because that form is unambiguously an instruction to send something. A BARE `word` is not
    flagged — it is usually a correct reference to a field, a status or a command, and telling those
    apart would need guessing. `taskops_update status=released` does not trip it either: the first word
    inside the backticks is the command, and what follows it is a space rather than a separator.

    Verified by appending the removed sentence to a real description and watching this fail.
    """
    import re

    tick = chr(96)
    pattern = tick + r"(\w+)\s*[:=][^" + tick + r"]*" + tick
    schema = next(t["inputSchema"] for t in listing() if t["name"] == tool.name)
    invented = sorted(set(re.findall(pattern, tool.description)) - set(schema["properties"]))
    assert not invented, (f"{tool.name} tells agents to pass fields it does not accept: {invented}")


def test_the_context_tool_answers_project_wide_and_per_card(tmp_path: Path) -> None:
    """The tool the manager makes its FIRST call, wired end to end.

    It sat in the use cases with no way for an agent to reach it, which is the failure this
    checks: a capability nothing advertises is a capability nobody has.

    `owner` on the objective is 0.5.0 and not a detail: an objective belongs to one person now,
    because the PROJECT's north is a milestone. An ownerless one is refused at the write door —
    it used to be accepted and then read by nothing, filed under a dev that does not exist.
    """
    from taskops.usecases import context_state, init, plan

    init(tmp_path, install_git_hooks=False)
    open_chapter(tmp_path, "the chapter these tests plan into",
                 actor="dev:berna")
    context_state(tmp_path, "objective", "ship 0.4 by Friday", owner="dev:berna",
                  actor="dev:berna")
    context_state(tmp_path, "decision", "never break the frozen contract", actor="dev:berna")
    created = plan(tmp_path, [{"title": "Wire the tool", "spec": "x"}],
                   actor="dev:berna")["created"]

    whole = call("taskops_context", {"repo_path": str(tmp_path)})
    assert "isError" not in whole
    assert "ship 0.4 by Friday" in text_of(whole)

    sliced = call("taskops_context", {"repo_path": str(tmp_path), "task": created[0]["id"]})
    assert "isError" not in sliced
    assert "never break the frozen contract" in text_of(sliced), "the slice dropped an invariant"


def test_the_context_tool_carries_its_write_half() -> None:
    """It did not, and the omission was mistaken for a rule.

    "An agent cannot restate an objective" was enforced by leaving the fields off this schema —
    which protected nothing, because a worker holds `Bash` and `taskops context objective …`
    was always one call away. Meanwhile the ORCHESTRATOR, the one caller with any business
    setting an objective, had to shell out for it. The fence moved to the use case, where it
    holds for every transport; the test that this surface stays read-only is gone with it, and
    `test_a_worker_may_not_state_a_standing_fact` below is what replaced it.

    Five write fields and not eight: `--horizon` and `--files` stay CLI-only, because every field
    here costs every connected agent context on every call.

    `mine` is GONE and `level`/`milestone` arrived with it — 0.5.0, and the change is the model
    rather than the surface. `mine` said "file this under me", and it had to, because `objective`
    could mean the project's north OR one dev's. The project's north is a MILESTONE now, so
    `state=objective` is unambiguously the caller's own and the flag had nothing left to say.
    What replaced it is `level`: whether a fact dies with its chapter or stands forever, which is
    the question the caller is the only one who can answer.
    """
    schema = next(t["inputSchema"] for t in listing() if t["name"] == "taskops_context")
    assert set(schema["properties"]) == {"repo_path", "task", "actor", "state", "text", "labels",
                                        "retire", "level", "milestone"}


def test_a_worker_may_not_state_a_standing_fact(tmp_path: Path) -> None:
    """THE rule, asserted where it now lives — and it is stronger than the schema ever was:
    this refuses the `Bash` route too, which is the one an agent would actually have taken."""
    from taskops._errors import BadRequest
    from taskops.usecases import context_state, init

    init(tmp_path, install_git_hooks=False)
    open_chapter(tmp_path, "the chapter these tests plan into",
                 actor="dev:berna")

    with pytest.raises(BadRequest) as refused:
        context_state(tmp_path, "objective", "ship it by Friday", actor="agent:ana/w1")
    # `actor` is on the schema for exactly this: a caller that could not name itself would
    # resolve from git config and arrive as the developer, and the fence would never fire.
    assert "actor" in next(t["inputSchema"] for t in listing()
                           if t["name"] == "taskops_context")["properties"]
    # The wording carries the level now ("a project or chapter objective"), because that is the
    # distinction 0.5.0 added: the refusal is about facts nobody owns, and a worker MAY state its
    # own dev's objective. What is asserted is the rule, not the sentence.
    assert "may not state a project or chapter objective" in str(refused.value)
    # The positive control carries an OWNER, because 0.5.0 has no unowned objective: the project's
    # north is a milestone, and one filed under nobody was read by nothing.
    assert context_state(tmp_path, "objective", "ship it", owner="dev:ana",
                         actor="dev:ana")["text"] == "ship it"


def test_update_advertises_evidence_and_its_argued_exemption() -> None:
    """Both halves or neither. `evidence` with no way out gets satisfied by a made-up sentence,
    and the escape hatch with no field to carry the reason is an unaudited bypass."""
    schema = next(t["inputSchema"] for t in listing() if t["name"] == "taskops_update")
    assert "evidence" in schema["properties"]
    assert "no_evidence" in schema["properties"]


def test_planning_a_card_with_acceptance_criteria_over_the_wire(tmp_path: Path) -> None:
    """The field a manager fills in, through the real schema and the real dispatch."""
    from taskops.usecases import init
    from taskops.usecases.acceptance import acceptance_for

    init(tmp_path, install_git_hooks=False)
    open_chapter(tmp_path, "the chapter these tests plan into",
                 actor="dev:berna")
    criterion = "WHEN the card is closed, THE SYSTEM SHALL demand evidence"
    planned = call("taskops_plan", {"repo_path": str(tmp_path),
                                    "tasks": [{"title": "Evidence", "spec": "x",
                                               "acceptance": [criterion]}]})
    assert "isError" not in planned
    listed = call("taskops_report", {"repo_path": str(tmp_path)})
    task_id = [w for w in text_of(listed).split() if w.startswith("tk-")][0]
    assert acceptance_for(tmp_path, task_id)["criteria"] == [criterion]


def test_a_specialist_that_forgets_its_actor_is_not_refused_its_own_card(
        tmp_path: Path) -> None:
    """THE bug this exists for, end to end over the wire.

    Four times a sub-agent claimed a card with `actor=agent:...` and then sent the update
    without one — resolving to the developer's `dev:<name>` and being refused a lease it
    was holding. Here the second call carries no actor at all and still works, because the
    card names its own worker.
    """
    from taskops.engine.scheduler import MACHINE
    from taskops.usecases import capture, init
    from taskops.usecases._project import project

    init(tmp_path, install_git_hooks=False)
    open_chapter(tmp_path, "the chapter these tests plan into",
                 actor="dev:berna")
    task = str(capture(tmp_path, "Wire it", spec="x", assign="agent:berna/api",
                       actor="dev:berna")["task"]["id"])

    claimed = call("taskops_next", {"repo_path": str(tmp_path), "task": task})
    assert "isError" not in claimed

    moved = call("taskops_update", {"repo_path": str(tmp_path), "task": task,
                                    "status": "review", "comment": "on it"})
    assert "isError" not in moved

    with project(tmp_path) as store:
        events = store.events.of_task(task)
    # The ENGINE's own moves are excluded, not the assertion loosened. `unblock` records the
    # promotion that made this card pickable, under `MACHINE` — the same actor `sweep_dead` has
    # always used — so a bookkeeping row now sits beside the agent's. What this test guards is
    # narrower and unchanged: an agent that sends no actor must not have its identity resolved
    # to its DEVELOPER's, because that is what cost it the lease it was holding. A `taskops`
    # row is the engine saying so about itself, and cannot be the bug.
    actors = {e["actor"] for e in events
              if e["kind"] in ("claimed", "status", "comment") and e["actor"] != MACHINE}
    assert actors == {"agent:berna/api"}
    assert "inferred" in {e["kind"] for e in events}


def test_evidence_survives_the_wire(root: Path) -> None:
    """The bug that burned a live run: `update_` built its kwargs by hand and left `evidence`
    and `no_evidence` out, so every close carrying evidence failed 'nothing says they were
    met' — the field crossed the wire and died one line short of the engine. Driven over real
    JSON-RPC because that is where it died; a unit test on the use case passes either way."""
    from taskops.usecases import next_task, plan

    made = plan(root, [{"title": "t", "spec": "s",
                        "acceptance": ["WHEN x THE SYSTEM SHALL y"]}], actor="dev:ana")
    card = made["created"][0]["id"]
    next_task(root, task=card, actor="agent:ana/w1")
    call("taskops_update", {"repo_path": str(root), "task": card, "actor": "agent:ana/w1",
                            "status": "review", "comment": "round 1"})

    closed = call("taskops_update", {"repo_path": str(root), "task": card,
                                     "actor": "agent:ana/verifier", "status": "done",
                                     "no_code": True, "comment": "verified",
                                     "evidence": "WHEN x THE SYSTEM SHALL y: ran it"})
    assert not closed.get("isError"), closed


def test_the_update_schema_declares_the_actor() -> None:
    """A schema is a fence: a strict host prunes params it does not declare, so without this
    field a sub-agent literally could not say who it was on the one call where identity
    decides everything."""
    tools = {t["name"]: t for t in listing()}
    fields = tools["taskops_update"]["inputSchema"]["properties"]
    assert "actor" in fields
    assert "evidence" in fields


def test_the_context_tool_files_an_objective_under_its_caller_with_no_flag(
        tmp_path: Path) -> None:
    """WHOSE fact it is, decided by the SORT and never by a flag. `mine` is gone (0.5.0).

    It said two different things on one tool — "file this under me" on a write, "show my page" on
    a read — and it had to, because `objective` could mean the project's north OR one dev's. The
    north is a MILESTONE now, so `state=objective` is unambiguously the caller's own and the flag
    had nothing left to say. What this pins is the consequence: ana's objective reaches ana's page
    and not juan's, with nobody typing an owner.

    A `note` goes the other way and that is the same decision read from the other side: through
    this tool it is the CHAPTER's, so both of them see it. A note of one's own is `taskops me
    note` — a person's command, at a terminal, which is where a private scratchpad belongs.
    """
    from taskops.transports.mcp._context import context_
    from taskops.usecases import init

    init(tmp_path, install_git_hooks=False)
    open_chapter(tmp_path, "the chapter these tests plan into",
                 actor="dev:berna")
    args = {"repo_path": str(tmp_path), "actor": "dev:ana"}

    context_({**args, "state": "note", "text": "the CSV is latin-1"})
    context_({**args, "state": "objective", "text": "ship the importer"})

    assert "ship the importer" in context_(args), "ana's page carries ana's objective"
    juan = context_({"repo_path": str(tmp_path), "actor": "dev:juan"})
    assert "ship the importer" not in juan, "and juan's does not"
    assert "the CSV is latin-1" in juan, "but the chapter's note reaches both"
