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

from ...render import render_inbox, render_opening
from ...usecases import check_command, checkout, inbox, track
from ...usecases.opening import opening
from ._args import cwd, session_of
from ._door import unfinished_verdict

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

    It used to inject what the session HELD, which for a fresh conversation is nothing, and
    ended with "Run taskops_next to claim one." That sentence is why two real sessions did the
    work themselves and left their cards dead in review: the first thing the main agent read
    told it to be a worker. SessionStart fires for the main conversation only — sub-agents
    never see it — so this event is the proof of which one is reading, and the role can be
    stated as a fact instead of hoped for in a prompt.
    """
    said = render_opening(cast("dict[str, Any]", opening(cwd(payload),
                                                         session=session_of(payload))))
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
    """The net at the door, then the auto-standup.

    A turn may not END with a half-done card. The refusal comes here — at Stop for the main
    conversation, at SubagentStop for the workers, which is where the forgetting actually
    happens: a worker is a sub-agent, and the main Stop never fires for it. Same judgement for
    both; only the payload differs (`agent_type` narrows a SubagentStop to the one stopping,
    so a verifier is never held at the door over a parallel worker's card).

    An instruction is not a mechanism — that lesson is carved into this codebase four times
    over — and "remember to close your card" was an instruction. This is the mechanism.
    """
    verdict = unfinished_verdict(payload) or _reviews_pending(payload)
    if verdict:
        return verdict
    checkout(cwd(payload), summary="Session ended.", session=session_of(payload))
    return {}


def _reviews_pending(payload: dict[str, Any]) -> dict[str, Any]:
    """Hold the turn while cards this session finished sit unverified.

    ONLY reviews. Blocking on everything `attention` reports would trap a person who asked a
    question into doing a board's worth of work before they could get an answer — but a card
    in `review` is work this session already started, and letting the turn end on it is the
    exact shape of the two cards that died.

    The same BLOCK_LIMIT that governs `unfinished`, for the same reason: an agent that has read
    the message twice will not act on a third copy, and a trapped session is a worse failure
    than a stale board.
    """
    try:
        from ...usecases._routing import whoami
        from ...usecases.pending import unverified, verify_text
        from ...usecases.unfinished import should_block

        where = cwd(payload)
        # WHOSE reviews. A session is blocked until it acts on this list, so a card in it that
        # belongs to another dev is not a nudge, it is an order to do refused work.
        rows = unverified(where, actor=whoami(where, ""))
        if not rows or not should_block(where, session_of(payload), "unverified-reviews"):
            return {}
        return {"decision": "block", "reason": verify_text(rows, closing=True)}
    except Exception:  # noqa: BLE001 — never trap a session at the door over our own bug
        return {}





def _context(event: str, text: str) -> dict[str, Any]:
    """The inject-context shape, or {} for nothing to inject."""
    if not text:
        return {}
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


def input_of(payload: dict[str, Any]) -> dict[str, Any]:
    found: object = payload.get("tool_input")
    return cast("dict[str, Any]", found) if isinstance(found, dict) else {}



