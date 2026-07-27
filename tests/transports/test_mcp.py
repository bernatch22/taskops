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

    init(tmp_path, install_git_hooks=False)
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
    result = call("taskops_plan", {"repo_path": str(tmp_path),
                                   "tasks": '[{"title": "From a string", "spec": "x"}]'})
    assert "isError" not in result
    assert "From a string" in text_of(result)
