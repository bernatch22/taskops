"""The net at the door: a turn may not END with a half-done card.

Split from `events.py` when the code budget refused it, and the split reads true: `events` is
what each hook event MEANS, and this is one judgement two of them share. Stop fires for the
main conversation; SubagentStop for the workers — which is where the forgetting actually
happens, because a worker is a sub-agent and the main Stop never fires for it.
"""

from __future__ import annotations

from typing import Any

from ._args import cwd, session_of

__all__ = ["unfinished_verdict", "subagent_stop"]


def subagent_stop(payload: dict[str, Any]) -> dict[str, Any]:
    """The net WITHOUT the standup. A worker finishing is not the session ending, and a
    shared handler was posting "Session ended." onto every card each time any sub-agent
    returned — a checkout per worker on a five-worker dispatch is five lies about one session.
    """
    return unfinished_verdict(payload)


def unfinished_verdict(payload: dict[str, Any]) -> dict[str, Any]:
    """`{"decision": "block", ...}` while the stopper owes the board, `{}` once it does not.

    FAILS OPEN on anything unexpected: a taskops bug may never trap a session at the door.
    FAILS CLOSED only on the exact case it exists for, and even that walks after the limit —
    an agent that has read the message twice is not going to act on a third copy, so it
    leaves, and the walk-away is written on the card where the board can show it instead of a
    silent `claimed` about nobody.
    """
    try:
        from ...usecases.session import track
        from ...usecases.unfinished import owed, should_block

        where = cwd(payload)
        session = session_of(payload)
        rows = owed(where, session, str(payload.get("agent_type", "") or ""))
        blocking = [row for row in rows if should_block(where, session, row["task"])]
        if not blocking:
            for row in rows:
                track(where, task=row["task"], session=session,
                      summary="left without closing — blocked twice at the door and let go")
            return {}
        return {"decision": "block", "reason": _owed_text(blocking)}
    except Exception:  # noqa: BLE001 — see the docstring: never trap a session over our bug
        return {}


def _owed_text(rows: list[dict[str, Any]]) -> str:
    """The message IS the fix — both exits, exactly, per card. A block that only says "no"
    teaches an agent to argue with the door instead of walking through it."""
    lines = ["You are not done — the board still shows work in your hands:"]
    for row in rows:
        lines.append(f"- {row['task']} ({row['status']}, {row['commits']} commit(s)) "
                     f"\u201c{row['title']}\u201d")
        lines.append(f"    finished?  taskops_update task={row['task']} actor={row['actor']} "
                     f"status=review comment=\"<what you did, per criterion>\"")
        lines.append(f"    stuck?     taskops_update task={row['task']} actor={row['actor']} "
                     f"status=ready comment=\"<where you got to and why you stopped>\"")
    return "\n".join(lines)
