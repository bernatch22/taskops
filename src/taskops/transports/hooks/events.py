"""One Claude Code hook event -> the JSON object the harness reads back.

Split from `claude` the same way `mcp/dispatch` is split from `mcp/protocol`: that module is
the wire (read stdin, route, write stdout), and this one is what each event MEANS. Every
handler here returns `{}` when there is nothing to say, and that silence is load-bearing —
these fire on every tool call, so a handler that always spoke would inject noise into a
session hundreds of times.

This is also where `brief`/`inbox`/`track`/`checkout` ended up. They used to be four CLI
commands a hook line typed one at a time; the events call the same use cases directly, so the
commands were a spelling of this file that a person could reach and nobody should.
"""

from __future__ import annotations

from typing import Any, cast

from ...render import render_brief, render_inbox
from ...usecases import brief, check_command, checkout, inbox, track

__all__ = ["pre_tool_use", "post_tool_use", "session_start", "stop"]


def pre_tool_use(payload: dict[str, Any]) -> dict[str, Any]:
    """Guard a `git commit`; pass everything else straight through.

    The matcher can only filter on the TOOL name, so this runs on every Bash call — which is
    why the not-a-commit path must be free, and why recognising a commit belongs to the use
    case rather than being reimplemented here.
    """
    command = str(input_of(payload).get("command", ""))
    verdict = check_command(cwd(payload), command)
    if verdict is None:
        return {}
    if not verdict.allowed:
        return _deny(verdict.reason)
    if verdict.command and verdict.command != command:
        return _rewrite(verdict.command)
    return {}


def _deny(reason: str) -> dict[str, Any]:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny",
                                   "permissionDecisionReason": f"taskops: {reason}"}}


def _rewrite(command: str) -> dict[str, Any]:
    """Allow, with the trailer injected. The reason is given, so the edit is never silent —
    an agent whose command was changed underneath it deserves to be told which and why."""
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "allow",
        "permissionDecisionReason": "taskops: added the Task trailer to bind this commit",
        "updatedInput": {"command": command}}}


def session_start(payload: dict[str, Any]) -> dict[str, Any]:
    """Inject what this session holds and who messaged it."""
    said = render_brief(brief(cwd(payload), session=session_of(payload)))
    return _context("SessionStart", said)


def post_tool_use(payload: dict[str, Any]) -> dict[str, Any]:
    """Two jobs on the cheapest hook: report activity, and deliver new messages.

    This is what makes agent-to-agent messaging feel immediate — a message written by another
    agent reaches this one on its very next tool call. Both halves are one indexed query, and
    both are usually zero rows, because anything expensive here taxes every tool call an agent
    ever makes.
    """
    where = cwd(payload)
    track(where, summary=_summary(payload), session=session_of(payload))
    return _context("PostToolUse", render_inbox(inbox(where)))


def _summary(payload: dict[str, Any]) -> str:
    """What the live board shows as "doing": the tool, and the file or command it touched."""
    tool = str(payload.get("tool_name", "?"))
    target = input_of(payload).get("file_path") or input_of(payload).get("command") or ""
    return f"{tool} {str(target)[:60]}".strip()


def stop(payload: dict[str, Any]) -> dict[str, Any]:
    """The auto-standup: post the session's own account to every task it holds."""
    checkout(cwd(payload), summary="Session ended.", session=session_of(payload))
    return {}


def _context(event: str, text: str) -> dict[str, Any]:
    """The inject-context shape, or {} for nothing to inject."""
    if not text:
        return {}
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


def input_of(payload: dict[str, Any]) -> dict[str, Any]:
    found: object = payload.get("tool_input")
    return cast("dict[str, Any]", found) if isinstance(found, dict) else {}


def cwd(payload: dict[str, Any]) -> str:
    """Where the session is. Defaults to "." so a hand-run hook still works."""
    return str(payload.get("cwd") or ".")


def session_of(payload: dict[str, Any]) -> str:
    return str(payload.get("session_id") or "")
