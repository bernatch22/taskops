"""One Claude Code hook event -> the JSON object the harness reads back.

Split from `claude` the same way `mcp/dispatch` is split from `mcp/protocol`: that module is
the wire (read stdin, route, write stdout), and this one is what each event MEANS. Every
handler here returns `{}` when there is nothing to say, and that silence is load-bearing —
these fire on every tool call, so a handler that always spoke would inject noise into a
session hundreds of times.

Also where `brief`/`inbox`/`track`/`checkout` ended up: four CLI commands a hook line typed one
at a time, now the same use cases called directly. And `SessionStart` is the one event with TWO
audiences — `additionalContext` reaches the model, `systemMessage` the person's terminal.
"""

from __future__ import annotations

from typing import Any, cast

from ...render import render_greeting, render_inbox, render_opening
from ...usecases import check_command, checkout, inbox, track
from ...usecases.opening import opening
from ._args import cwd, session_of
from ._door import reviews_pending, unfinished_verdict

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
    """Inject the ROLE, the project's standing facts, and what is waiting on a decision.

    It used to end with "Run taskops_next to claim one", and that sentence is why two real
    sessions did the work themselves and left their cards dead in review: the first thing the
    main agent read told it to be a worker. SessionStart fires for the main conversation only,
    so this event PROVES which one is reading and the role is stated as a fact.
    """
    view = cast("dict[str, Any]", opening(cwd(payload), session=session_of(payload)))
    return _spoken(_context("SessionStart", render_opening(view)), render_greeting(view))


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
    """The net at the door, then the auto-standup.

    A turn may not END with a half-done card. The refusal comes here — at Stop for the main
    conversation, at SubagentStop for the workers, which is where the forgetting actually
    happens: a worker is a sub-agent, and the main Stop never fires for it. Same judgement for
    both; only the payload differs (`agent_type` narrows a SubagentStop to the one stopping,
    so a verifier is never held at the door over a parallel worker's card).

    An instruction is not a mechanism — that lesson is carved into this codebase four times
    over — and "remember to close your card" was an instruction. This is the mechanism.
    """
    verdict = unfinished_verdict(payload) or reviews_pending(payload)
    if verdict:
        return verdict
    checkout(cwd(payload), summary="Session ended.", session=session_of(payload))
    return {}


def _spoken(reply: dict[str, Any], line: str) -> dict[str, Any]:
    """The one line the PERSON sees — `systemMessage` is the only field that reaches a terminal.
    `additionalContext` is wrapped in a reminder they never see, and stdout is hidden too."""
    return {**reply, "systemMessage": line} if line else reply


def _context(event: str, text: str) -> dict[str, Any]:
    """The inject-context shape, or {} for nothing to inject."""
    if not text:
        return {}
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


def input_of(payload: dict[str, Any]) -> dict[str, Any]:
    found: object = payload.get("tool_input")
    return cast("dict[str, Any]", found) if isinstance(found, dict) else {}



