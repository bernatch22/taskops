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

from . import hello, tools
from .. import _clock
from .._json import as_object
from ..board import find_root, open_board
from .boards import Boards
from .._errors import TaskopsError

INSTRUCTIONS = """
This project's work lives on a shared taskops board (milestones → cards). The
board is the truth, not this transcript.

ORCHESTRATOR (dev:<name>, the main session): plan with taskops_plan (one call,
whole tree, rules=[…] travel into every take) · fanning out onto one surface?
land the shared seams — types, helpers, the shell — in ONE serialized card
FIRST: parallel workers branch before they exist and search finds nothing · and if that surface has a GENERATED artifact committed (a
built bundle), ONE card rebuilds it at the end — N cards rebuilding it is N-1
conflicts by construction · dispatch with taskops_assign,
then spawn one sub-agent per brief, all in one message · integrate a done card
with taskops_merge task= · land a FINISHED milestone with taskops_merge
milestone= — NEVER raw git in the shared checkout · review is optional per
card (review=true / reviews=true): a submitted card needs a verifier whose one
tool is taskops_review (task= claims, verdict=pass|changes note= judges); pass
→ YOU close it, changes → resume your worker with the note · you may NOT hold
a card.

WORKER (spawned sub-agent): pass actor=agent:<dev>/<name> (your brief names
it) on EVERY taskops call — all sub-agents share this ONE server · taskops_take
returns everything, ordered; work in that worktree · done needs a card-bound
commit or no_code=true + note (a commit needs NO card: card-less ones are
recorded at project level) · review=true card → hand IN: status=review note=…,
stay reachable · stuck → status=released note=… — never silence · update
changes the card, comment talks: you may write on ANY open card, and a ✉ in
the pulse line means you were named — answer on that card and it clears (no mark-as-read) · never git switch / merge / push main / touch another worktree.

Branches are inhabited, not switched. The human's dashboard: `taskops ui`.
""".strip()


def serve(boards: Boards, stdin: TextIO, stdout: TextIO) -> None:
    """Read a request per line, answer a response per line, until EOF."""
    for line in stdin:
        if not line.strip():
            continue
        response = handle(boards, line)
        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()


def handle(boards: Boards, line: str) -> dict[str, Any] | None:
    try:
        request = as_object(json.loads(line))
    except ValueError:
        return _error(None, -32700, "that was not JSON")
    ident = request.get("id")
    method = str(request.get("method", ""))
    params = as_object(request.get("params"))

    if method == "initialize":
        return _ok(ident, hello.hello(boards.at('')[0], INSTRUCTIONS))
    if method.startswith("notifications/"):
        return None  # a notification has no reply, by definition
    if method == "ping":
        return _ok(ident, {})
    if method == "tools/list":
        return _ok(ident, {"tools": [hello.describe(t) for t in tools.TOOLS]})
    if method == "tools/call":
        return _call(boards, ident, params)
    return _error(ident, -32601, f"this server has no method {method!r}")


def _call(boards: Boards, ident: object, params: dict[str, Any]) -> dict[str, Any]:
    name = str(params.get("name", ""))
    args = as_object(params.get("arguments"))
    # Pulled out BEFORE the verb sees it: where a call GOES is the server's
    # question, and no verb has a `repo_path` argument to answer it with.
    where = str(args.pop("repo_path", "") or "")
    try:
        board, repo = boards.at(where)
        text = tools.call(board, repo, name, args, _clock.now())
    except TaskopsError as err:
        # A refusal is a RESULT, not a protocol error: the agent must read it.
        return _ok(ident, {"content": [_text(f"✗ {err}")], "isError": True})
    except Exception as err:  # noqa: BLE001 — a tool bug must not kill the session's server
        # Unexpected ≠ unanswerable: an exception that escaped here used to end
        # the stdio loop, taking every later call of the session down with it.
        return _ok(ident, {"content": [_text(f"✗ taskops broke on {name}: {err!r}")], "isError": True})
    return _ok(ident, {"content": [_text(text)]})


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
    boards = Boards(board, repo, who)
    serve(boards, sys.stdin, sys.stdout)
    boards.close()
    return 0
