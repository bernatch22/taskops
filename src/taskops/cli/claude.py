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
immediacy: `core/mentions.pending()` still derives, the pulse line still rides
on every tool result, the MENTIONS group still renders. What it buys is the one
thing those cannot — reaching a worker that is twenty minutes deep in Edit and
Bash calls and will not touch a taskops tool until it is done.

Four properties make that safe, and each one is a test:

* it calls `mentions`, the only read that does not renew a lease, so delivering
  to a worker cannot keep a dead worker's card out of STALLED;
* it is throttled to one look per reader per 30s, stamped in a gitignored file;
* every failure path is silence and exit 0 — no output, no stderr, nothing;
* it emits nothing at all when there is nothing to say, which is almost always.
"""

from __future__ import annotations

import os
import re
import sys
import json
from typing import Any
from pathlib import Path

from .. import _clock
from .._json import text, as_rows, as_object
from ..board import DIR, find_root, is_project, open_board

STAMP = "hook-seen.json"  # <repo>/.taskops/ — gitignored by install.IGNORED
THROTTLE = 30.0  # seconds per reader. A round trip per Edit is v1's latency bug.
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
    who, for_task = _reader(payload, cwd)
    if not _due(root, f"{who} {for_task}"):
        return
    answer = _ask(root, who, for_task)
    lines = _lines(text(answer.get("actor")) or who, as_rows(answer.get("mentions")))
    if not lines:
        return  # silence costs zero context, and this fires on every tool call
    _emit(text(payload.get("hook_event_name")) or DEFAULT_EVENT, lines)


def _reader(payload: dict[str, Any], cwd: str) -> tuple[str, str]:
    """Who this turn belongs to: the actor, and the card that may name them.

    `TASKOPS_ACTOR` wins when the hook process happens to have it. It usually
    does not: a hook is spawned by the host, not by the worker, so it inherits
    the session's environment and not the sub-agent's. What it does see is the
    sub-agent's own tool calls, and every one of those touches its worktree —
    so the path names the card, and the board (`verbs/pulse._addressee`) turns
    the card into its holder. Neither → `dev:$USER`, the orchestrator.
    """
    given = os.environ.get("TASKOPS_ACTOR", "")
    if given:
        return given, ""
    blob = json.dumps(payload.get("tool_input", "")) + " " + cwd
    found = WORKTREE.search(blob)
    return f"dev:{os.environ.get('USER', 'me')}", found.group(1) if found else ""


def _due(root: Path, key: str) -> bool:
    """One look per reader per 30s, and the stamp is written BEFORE the board is
    asked — so a board that is down or slow is not retried once per keystroke."""
    path = root / DIR / STAMP
    now = _clock.now()
    seen: dict[str, Any] = {}
    if path.exists():
        try:
            seen = as_object(json.loads(path.read_text(encoding="utf-8")))
        except ValueError:
            seen = {}  # a broken stamp means "never looked", never a crash
    last = seen.get(key)
    if isinstance(last, (int, float)) and 0.0 <= now - float(last) < THROTTLE:
        return False
    seen[key] = now
    path.write_text(json.dumps(seen), encoding="utf-8")
    return True


def _ask(root: Path, who: str, for_task: str) -> dict[str, Any]:
    """Through `Board` like every other caller — local or remote, same door.

    `mentions` is a read that renews nothing, which is what makes it legal to
    call on somebody else's behalf; `board` would renew the lease of a worker
    that may have died an hour ago.
    """
    board = open_board(root, who, TIMEOUT)
    try:
        return board.call("mentions", {"for_task": for_task} if for_task else {})
    finally:
        board.close()


def _lines(actor: str, rows: list[dict[str, Any]]) -> str:
    """One line per mention, naming the addressee rather than saying "you": the
    reader may be the orchestrator, and the card may have been resolved from a
    worktree path that belongs to somebody else."""
    return "\n".join(
        f"✉ taskops: {row.get('by')} mentioned {actor} on {row.get('id')} "
        f"“{_trim(row.get('text'))}” — reply on the card "
        f'(taskops_comment task={row.get("id")} text="…") and it clears.'
        for row in rows
    )


def _trim(body: object) -> str:
    """A line, not the comment: the whole text is one taskops_card away, and
    this is injected into a transcript that is doing something else."""
    line = " ".join(str(body or "").split())
    return f"{line[:157]}…" if len(line) > 158 else line


def _emit(event: str, context: str) -> None:
    """The contract verified against the Claude Code hooks reference: JSON on
    stdout is parsed only on exit 0, and `hookSpecificOutput.additionalContext`
    is wrapped in a system reminder and inserted where the hook fired.
    `hookEventName` must echo the event that fired, so it is taken from the
    payload rather than assumed — plain stdout is added to the transcript for
    `UserPromptSubmit` but only logged for `PostToolUse`, so the JSON form is
    the only one that works for both.
    """
    print(
        json.dumps(
            {"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}},
            ensure_ascii=False,
        )
    )
