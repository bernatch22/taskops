"""The nets at the door: a turn may not END with a half-done card, or with a review nobody took.

Split from `events.py` when the code budget refused it, and the split reads true: `events` is
what each hook event MEANS, and these are the judgements it applies. Stop fires for the
main conversation; SubagentStop for the workers — which is where the forgetting actually
happens, because a worker is a sub-agent and the main Stop never fires for it.

The two nets are NOT symmetric, and the asymmetry is the whole of what the second one learned:
an unfinished card is something the session can finish right now, so it is worth blocking twice.
A review is DELEGATED, so a second block lands before the sub-agent it asked for could prove
anything — see `reviews_pending`.
"""

from __future__ import annotations

from typing import Any

from ._args import cwd, session_of

__all__ = ["unfinished_verdict", "reviews_pending", "subagent_stop"]


def subagent_stop(payload: dict[str, Any]) -> dict[str, Any]:
    """The unfinished-card net, and NOTHING ELSE. A worker finishing is not a session ending.

    This hook used to also ask for a verifier, and the ask was addressed to the wrong reader.
    `SubagentStop` injects into the context of the SUB-AGENT that just stopped — a worker,
    whose tools are taskops plus Read/Write/Edit/Bash. Spawning a sub-agent is the
    orchestrator's capability alone. So a worker read "spawn a `taskops-verifier` for this
    card", could not, said so, was asked again, and spent four turns explaining to nobody that
    it lacks the tool. An instruction delivered to somebody who cannot act on it is worse than
    silence: it costs turns and it teaches the reader that this channel talks nonsense.

    The ask belongs to `Stop`, which fires for the MAIN conversation — the orchestrator, the
    one reader that can actually spawn — and that is where it lives now.
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


def reviews_pending(payload: dict[str, Any]) -> dict[str, Any]:
    """Hold the turn while cards this session finished sit unverified.

    ONLY reviews. Blocking on everything `attention` reports would trap a person who asked a
    question into doing a board's worth of work before they could get an answer — but a card
    in `review` is work this session already started, and letting the turn end on it is the
    exact shape of the two cards that died.

    ONCE PER CARD, and both halves of that are the fix for what a live session did with the old
    shape. It counted under ONE key for the whole session, so the second card got no message at
    all while the first got two — and the second of those arrived after the session had spawned the
    verifier, because a sub-agent claims the card in its own process a moment later. The session
    was blocked, said "ya está lanzado", was blocked again, and spent two turns arguing with a net
    that could not see what it had done. See `should_block`'s `limit`.
    """
    try:
        from ...usecases._routing import whoami
        from ...usecases.pending import unverified, verify_text
        from ...usecases.unfinished import should_block

        where = cwd(payload)
        # WHOSE reviews. A session is blocked until it acts on this list, so a card in it that
        # belongs to another dev is not a nudge, it is an order to do refused work.
        rows = unverified(where, actor=whoami(where, ""))
        session = session_of(payload)
        # Per CARD, and `limit=1`: a review is delegated, so a second block lands before anything
        # could prove the first one worked. A card this session has not been told about yet still
        # gets its message, which one shared bucket did not.
        fresh = [row for row in rows
                 if should_block(where, session, f"verify:{row['task']['id']}", limit=1)]
        if not fresh:
            return {}
        return {"decision": "block", "reason": verify_text(fresh, closing=True)}
    except Exception:  # noqa: BLE001 — never trap a session at the door over our own bug
        return {}
