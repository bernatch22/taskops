"""JSON-RPC, as a pure function: a message in, a response object out.

No socket and no stdin, so every method is testable by calling it — the transport work is
tested once, in `server`, instead of by every case that wants to know what `tools/call`
answers.
"""

from __future__ import annotations

from typing import Any

from ..._version import __version__
from .answers import Answer, failure
from .tools import listing

__all__ = ["PROTOCOL", "INSTRUCTIONS", "respond"]

PROTOCOL = "2024-11-05"

# Returned by `initialize` and injected into the calling agent's context ONCE. With tool
# search on, the SCHEMAS stay deferred until the agent goes looking, so this is the only
# taskops text a session is guaranteed to see. What belongs here is the mental model and
# the routing BETWEEN tools — never a restatement of each tool's own description — and it
# must stay short, because it costs context in every session that loads this server.
INSTRUCTIONS = """taskops is the shared task list for this repository. Tasks persist across sessions, machines and developers, so work you claim is work nobody else will start.

The loop, and it is short:
- taskops_next — claim work. Returns the spec, the branch to create, and a warning if another agent is editing the same files. Do this before coding, not after.
- taskops_update — progress, a comment, or `status=done`. `mentions` sends a message to another actor's agent; they see it within one tool call.
- taskops_ask — read a task in full before you touch a file you did not claim.

Two rules the server enforces rather than suggests. A commit must be on the claimed task's branch (`tk/<id>/<slug>`) — the trailer is added for you. And `done` requires a commit bound to the task, so the board cannot say finished about work that does not exist.

Your claim is a LEASE: every taskops call renews it, and if your process dies it expires and the task returns to the queue. If a write is refused for a missing lease, claim again — do not work around it."""


def respond(message: dict[str, Any]) -> dict[str, Any] | None:
    """The response to one message, or None if it deserves none.

    A message without an id is a notification, and answering one is a protocol violation
    some hosts read as a broken server. Returning before any work also means a notification
    can never cost a database open.
    """
    mid = message.get("id")
    if mid is None:
        return None
    return {"jsonrpc": "2.0", "id": mid, "result": _result(message)}


def _result(message: dict[str, Any]) -> dict[str, Any]:
    method = message.get("method", "")
    if method == "initialize":
        return {"protocolVersion": PROTOCOL, "capabilities": {"tools": {}},
                "serverInfo": {"name": "taskops", "version": __version__},
                "instructions": INSTRUCTIONS}
    if method == "tools/list":
        return {"tools": listing()}
    if method == "tools/call":
        params: dict[str, Any] = message.get("params") or {}
        return _content(_call(params))
    return {}


def _call(params: dict[str, Any]) -> Answer:
    """The engine is imported HERE, not at module scope.

    A host lists the tools before it asks anything, and that handshake must not pay for a
    sqlite connection or a git subprocess.
    """
    from .dispatch import call_tool

    try:
        return call_tool(str(params.get("name", "")),
                         dict(params.get("arguments") or {}))
    except Exception as err:                      # noqa: BLE001 — last resort
        # `call_tool` handles every failure it can name; anything reaching here is a bug,
        # and the agent still needs a sentence rather than a hang.
        return failure(f"{type(err).__name__}: {err}")


def _content(result: Answer) -> dict[str, Any]:
    payload: dict[str, Any] = {"content": [{"type": "text", "text": result.text}]}
    return {**payload, "isError": True} if result.failed else payload
