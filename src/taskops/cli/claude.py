"""`taskops hook claude` — the delivery hook. It reads; it never writes.

The third sibling of `hook trailer` and `hook commit`, under the same contract:
**never break the caller, never block, always exit 0.** A git hook that refuses
a commit and a Claude hook that stalls a turn are the same bug, and v1 shipped
both.

This is the one Claude hook this project has, added on 2026-08-06 by the person
who wrote the rule against them (MENTIONS.md §9). The rule did not disappear, it
NARROWED:

    a hook may DELIVER — it may never decide, never store, never write.

The board stays the only truth. Delete this file and nothing is lost but
immediacy: every group it names still derives and still renders, and the pulse
line still rides on every tool result. What it buys is the one thing those
cannot — reaching somebody twenty minutes deep in Edit and Bash calls who will
not touch a taskops tool until they are done.

Four properties make that safe, and each one is a test:

* it calls `mentions` and `waiting`, the only two reads that renew no lease, so
  delivering to a worker cannot keep a dead worker's card out of STALLED;
* it is throttled per reader, stamped in a gitignored file — 30s for a mention,
  `WAITING` for the orchestrator's groups (see there for why they differ);
* every failure path is silence and exit 0 — no output, no stderr, nothing;
* it emits nothing at all when there is nothing to say, which is almost always.

It delivers TWO things and is still ONE hook with one entry point — two would be
how v1 came to disagree with itself. To anybody: a pending MENTION. To a `dev:`
only: MERGE, REVIEW, STALLED (`verbs/_waiting.py`), added 2026-08-08 because
tk-342486 and tk-17d463 were dispatched here and their workers never spawned,
and both sat `stalled` — correctly derived and unread — for twelve minutes until
a human noticed from the dashboard. `assign` prepares and starts nothing; that
gap is what this delivers into, and a worker is told none of it because it
neither merges nor dispatches. Both halves are the same move: SAY what already
derives, name the call, decide nothing.

The board itself arrives through the MCP handshake (`mcp/server.py::_hello`),
which the host always loads and which needs no settings file to be trusted — a
SessionStart hook was tried for it on 2026-08-07 and removed the same day,
because two channels for one fact is how v1 came to disagree with itself.
"""

from __future__ import annotations

import os
import re
import sys
import json
from typing import Any
from pathlib import Path

from . import wording
from .. import _clock
from .._json import text, as_rows, as_object
from ..board import DIR, Board, find_root, is_project, open_board
from ..core.types import ROLE_DEV, role_of

STAMP = "hook-seen.json"  # <repo>/.taskops/ — gitignored by install.IGNORED
THROTTLE = 30.0  # seconds per reader. A round trip per Edit is v1's latency bug.
WAITING = 180.0
"""The orchestrator's groups, on their own clock: the failure they report is on
a different scale. A mention is urgent WITHIN a turn, so 30s is deliberately
smaller than one. A stalled card is not — the incident was TWELVE MINUTES of
silence, and three minutes bounds that to a quarter while never repeating the
same three lines inside one long turn of Edits. Rejected: 30s (a turn full of
tool calls would repeat them, and a hook that repeats itself is noise, which is
how a hook gets deleted); 600s (the incident's own scale — it would not have
caught the incident); per tool call (v1's latency bug: this costs a round
trip)."""
TIMEOUT = 2.0  # a remote board that is slow must cost the turn nothing
DEFAULT_EVENT = "PostToolUse"

# `<repo>/.taskops/trees/tk-a1b2c3` — a worktree is named after its card, and
# that is the whole chain by which a sub-agent can be identified at all.
WORKTREE = re.compile(r"\.taskops/trees/(tk-[0-9a-f]{6})\b")


def deliver(here: Path) -> int:
    """Always 0, whatever happened. This is the entire error policy.

    A mention system that can break a turn is worse than no mention system: the
    worst case here must be that somebody finds out one call later, through the
    pulse line, exactly as they did before this file existed.
    """
    try:
        _run(here)
    except Exception:  # every failure is silence — see the docstring
        return 0
    return 0


def _run(here: Path) -> None:
    payload = as_object(json.loads(sys.stdin.read() or "{}"))
    cwd = text(payload.get("cwd")) or str(here)
    root = find_root(Path(cwd))
    if not is_project(root):
        # No board here — and a hook must never make one. `Stores` mkdirs on
        # open, so a laxer guard turns a READ into a write: this fired in a
        # directory whose only `.taskops/` was v1's session file and left a
        # board behind. Found on the first real run, not by a test.
        return
    event = text(payload.get("hook_event_name")) or DEFAULT_EVENT
    who, for_task = _reader(payload, cwd)
    # Two throttles, one stamp file, and both are decided BEFORE the board is
    # opened: the common case is that neither is due and this costs a file read.
    ping = _due(root, f"✉ {who} {for_task}", THROTTLE)
    look = _orchestrating(who, for_task) and _due(root, f"◆ {who}", WAITING)
    if not (ping or look):
        return
    lines = _ask(root, who, for_task, ping, look)
    if not lines:
        return  # silence costs zero context, and this fires on every tool call
    wording.emit(event, "\n".join(lines))


def _orchestrating(who: str, for_task: str) -> bool:
    """A `dev:` reading its own session, and nothing else: `for_task` means the
    turn resolved to a sub-agent through its worktree path, and a worker neither
    merges nor dispatches. The verb refuses it too (`verbs/__init__.py`)."""
    return not for_task and role_of(who) == ROLE_DEV


def _reader(payload: dict[str, Any], cwd: str) -> tuple[str, str]:
    """Who this turn belongs to: the actor, and the card that may name them.

    `TASKOPS_ACTOR` wins when the hook process happens to have it. It usually
    does not: a hook is spawned by the host, so it inherits the session's
    environment and not the sub-agent's. What it does see is the sub-agent's own
    tool calls, and each touches its worktree — so the path names the card, and
    the board (`verbs/_mentions._addressee`) turns the card into its holder.
    Neither → `dev:$USER`, the orchestrator.
    """
    given = os.environ.get("TASKOPS_ACTOR", "")
    if given:
        return given, ""
    blob = json.dumps(payload.get("tool_input", "")) + " " + cwd
    found = WORKTREE.search(blob)
    return f"dev:{os.environ.get('USER', 'me')}", found.group(1) if found else ""


def _due(root: Path, key: str, every: float) -> bool:
    """One look per reader per `every` seconds, and the stamp is written BEFORE
    the board is asked — so a board that is down or slow is not retried once per
    keystroke. Each key has its own line in the stamp: a mention delivered must
    never silence the orchestrator's groups, nor the other way round."""
    path = root / DIR / STAMP
    now = _clock.now()
    seen: dict[str, Any] = {}
    if path.exists():
        try:
            seen = as_object(json.loads(path.read_text(encoding="utf-8")))
        except ValueError:
            seen = {}  # a broken stamp means "never looked", never a crash
    last = seen.get(key)
    if isinstance(last, (int, float)) and 0.0 <= now - float(last) < every:
        return False
    seen[key] = now
    path.write_text(json.dumps(seen), encoding="utf-8")
    return True


def _ask(root: Path, who: str, for_task: str, ping: bool, look: bool) -> list[str]:
    """Through `Board` like every other caller — same door, ONE connection
    however many groups are due. `mentions` and `waiting` are the two reads that
    renew nothing, which is what makes them legal to call on somebody else's
    behalf; `board` would renew the lease of a worker that died an hour ago and
    stamp its presence besides."""
    board = open_board(root, who, TIMEOUT)
    args = {"for_task": for_task} if for_task else {}
    try:
        answer = _read(board, "mentions", args) if ping else {}
        groups = as_object(_read(board, "waiting", {}).get("groups")) if look else {}
        actor = text(answer.get("actor")) or who
        return wording.lines(actor, as_rows(answer.get("mentions")), groups)
    finally:
        board.close()


def _read(board: Board, verb: str, args: dict[str, Any]) -> dict[str, Any]:
    """One group failing must not cost the other its delivery — a refusal, an
    old server that has never heard of `waiting`, a timeout on one call."""
    try:
        return board.call(verb, args)
    except Exception:
        return {}
