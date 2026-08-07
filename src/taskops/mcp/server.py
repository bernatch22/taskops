"""The MCP server: newline-delimited JSON-RPC on stdin/stdout.

`INSTRUCTIONS` below is layer 1 of the context injection (§2.3). The host loads
it before the first message of the session, so the role protocol arrives
without a single hook, a single file in the repo, or anything that can be
installed twice and drift.

A refused call comes back as `isError` with the refusal AS TEXT — an agent that
cannot read the way out will invent one.
"""

from __future__ import annotations

import os
import sys
import json
from typing import Any, TextIO
from pathlib import Path

from . import tools
from .. import _clock
from .._json import as_object
from ..board import Board, find_root, open_board
from .._errors import TaskopsError
from .._version import __version__

PROTOCOL = "2025-06-18"

INSTRUCTIONS = """
This project has a shared taskops board. Milestones hold cards; cards hold the
work. The board is the truth, and it lives on a server — not in this transcript.

If you are the main session you are the ORCHESTRATOR (dev:<name>):
  · open every turn with taskops_board — it says what the board is waiting for;
  · plan with taskops_plan (one call writes the whole tree, deps included).
    rules=[…] there is what holds for EVERY card of the chapter — it travels
    into every take, above the spec, so nobody builds against a rule unread;
  · dispatch with taskops_assign, then spawn ONE sub-agent per brief it
    returns, all in the same message. The brief is self-contained;
  · integrate finished cards with taskops_merge (into the milestone branch);
  · REVIEW is optional, per card (review=true, or reviews=true on the plan).
    A submitted card shows under REVIEW: spawn a verifier (an ordinary agent)
    that calls taskops_take review=true, then taskops_review verdict=… note=….
    verdict=pass → YOU close it (taskops_update status=done); verdict=changes
    → send the note back to the worker you spawned — it still has its context;
  · you may NOT hold a card. Cards are for workers.

If you are a spawned sub-agent you are a WORKER, and your identity travels IN
the call: pass actor=agent:<dev>/<name> (your brief names it) on EVERY taskops
call. Sub-agents share this session's MCP server, whose own identity is the
orchestrator's — omit actor= and the board refuses you as the wrong role.
  · taskops_take returns EVERYTHING in one call and nothing is truncated: the
    milestone's goal and its rules, the spec and criteria, the whole thread,
    who else is working right now, the previous worker's note, your worktree.
    Read it top-down — the order is deliberate, what changes what you do comes
    before the spec. Then work in that worktree → taskops_update status=done;
  · `done` needs a commit bound to the card (the Task: trailer is stamped by a
    git hook), or no_code=true with a note saying what happened instead. A
    commit does NOT need a card: one made outside any card is still recorded,
    at project level, and that is all the board knows about it;
  · a card with review=true is handed IN, never closed by you: taskops_update
    status=review note="what you did", then stay reachable — the verdict comes
    back through the orchestrator, and a `changes` note shows above the spec;
  · out of context or stuck → status=released note="what you got to". The next
    worker is shown that note verbatim. Silence is the one unacceptable end;
  · taskops_update changes the CARD (status, spec, criteria, priority, deps);
    taskops_comment says something on one. Two different moves, two tools;
  · never git switch, never merge, never push to main, never touch another
    card's directory.

TALKING TO THE OTHERS — you may always write on ANY open card, including one
somebody else holds, in another milestone, on another team. You never need to
own a card to leave a note on it:

    taskops_comment task=<any open card> text="…" mentions=["agent:<dev>/<x>"]

That is the direct channel between agents working in parallel, and it is the
move whenever your work meets somebody else's: taskops_take warns you which
cards claim the files you are about to edit — say so ON THAT CARD instead of
guessing, editing around them, or waiting. taskops_board shows what everybody
holds right now under DOING; taskops_card task=<id> reads any card in full,
and query=<text> searches every card's title and spec. Reading and commenting
are open to everyone; only taking, closing and releasing are the owner's.

A ✉ in the pulse line at the foot of any result means somebody addressed you
by name: taskops_board lists them under MENTIONS, taskops_card task=<id> reads
the thread. Answer on that card — writing anything on it clears the mention.
There is no mark-as-read.

Branches are not switched, they are inhabited: one directory per card, pinned
to its branch for life. `main` is written by a person, through a pull request,
and by nothing else.
""".strip()


def serve(board: Board, repo: Path, stdin: TextIO, stdout: TextIO) -> None:
    """Read a request per line, answer a response per line, until EOF."""
    for line in stdin:
        if not line.strip():
            continue
        response = handle(board, repo, line)
        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()


def handle(board: Board, repo: Path, line: str) -> dict[str, Any] | None:
    try:
        request = as_object(json.loads(line))
    except ValueError:
        return _error(None, -32700, "that was not JSON")
    ident = request.get("id")
    method = str(request.get("method", ""))
    params = as_object(request.get("params"))

    if method == "initialize":
        return _ok(ident, _hello())
    if method.startswith("notifications/"):
        return None  # a notification has no reply, by definition
    if method == "ping":
        return _ok(ident, {})
    if method == "tools/list":
        return _ok(ident, {"tools": [_describe(t) for t in tools.TOOLS]})
    if method == "tools/call":
        return _call(board, repo, ident, params)
    return _error(ident, -32601, f"this server has no method {method!r}")


def _call(board: Board, repo: Path, ident: object, params: dict[str, Any]) -> dict[str, Any]:
    name = str(params.get("name", ""))
    args = as_object(params.get("arguments"))
    try:
        text = tools.call(board, repo, name, args, _clock.now())
    except TaskopsError as err:
        # A refusal is a RESULT, not a protocol error: the agent must read it.
        return _ok(ident, {"content": [_text(f"✗ {err}")], "isError": True})
    except Exception as err:  # noqa: BLE001 — a tool bug must not kill the session's server
        # Unexpected ≠ unanswerable: an exception that escaped here used to end
        # the stdio loop, taking every later call of the session down with it.
        return _ok(ident, {"content": [_text(f"✗ taskops broke on {name}: {err!r}")], "isError": True})
    return _ok(ident, {"content": [_text(text)]})


def _hello() -> dict[str, Any]:
    return {
        "protocolVersion": PROTOCOL,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": "taskops", "version": __version__},
        "instructions": INSTRUCTIONS,
    }


def _describe(tool: tools.Tool) -> dict[str, Any]:
    return {"name": tool.name, "description": tool.description, "inputSchema": tool.schema}


def _text(body: str) -> dict[str, Any]:
    return {"type": "text", "text": body}


def _ok(ident: object, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": ident, "result": result}


def _error(ident: object, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": ident, "error": {"code": code, "message": message}}


def actor() -> str:
    """The worker's identity comes from the environment its brief exported."""
    return os.environ.get("TASKOPS_ACTOR") or f"dev:{os.environ.get('USER', 'me')}"


def main() -> int:
    repo = find_root(Path.cwd())
    who = actor()
    try:
        board = open_board(repo, who)
    except TaskopsError as err:
        sys.stderr.write(f"taskops: {err}\n")
        return 1
    # `Absent` when this repo has no board: the server is registered globally,
    # so it starts in every project there is. It must come up anyway (a failed
    # MCP server in twenty unrelated repos is noise nobody can act on), create
    # nothing, and let each tool answer with the `taskops init` line instead.
    sys.stderr.write(f"taskops mcp: {who} on {board.url or f'{repo} (no board — taskops init)'}\n")
    serve(board, repo, sys.stdin, sys.stdout)
    board.close()
    return 0
