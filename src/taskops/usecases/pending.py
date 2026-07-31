"""Reviews this session opened and nobody closed — the judgement behind the review-time net.

The failure it exists for, watched live on a real board: two developers told their sessions to
get to work, the workers finished, both cards landed in `review`, and there they sat. Nothing
was broken — the handover is supposed to release the card and wait for somebody else — but
"somebody else" was the same session, and nothing told it so. Two cards dead, an hour each.

`unfinished` is the sibling and the difference is whose turn it is. That module catches a card
still IN somebody's hands at the door. This one catches the opposite: a card the session
correctly let go of, which now needs a decision only that session is positioned to make.

Judgement only, like `unfinished` — the hook transport turns it into Claude Code's shapes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .._types import HUMAN, PEER
from .attention import attention

POLICIES = frozenset({HUMAN, PEER})
"""Reviewer values that say WHO may close, not WHAT to spawn. A policy in a spawn instruction
is an agent type that does not exist."""

__all__ = ["unverified", "verify_text"]


def unverified(start: Path | str, *, actor: str = "") -> list[dict[str, Any]]:
    """Every card sitting in `review` that THIS actor could actually pick up.

    Derived from `attention` rather than queried again, so there is one definition of "waiting
    for a verifier" and a board that disagrees with the sweep is impossible by construction.

    The `actor` is the whole correctness of the message. Without it this asked the board-wide
    question and the answer was pasted into one developer's turn: a Stop hook can then name a
    card routed to somebody else, and a session that is BLOCKED until it acts will act — it
    spawns a verifier, the verifier is refused at the close, and two agents are spent on a
    review that was never this dev's. Advice the engine will refuse is worse than no advice.
    """
    return [item for item in attention(start, actor=actor)["waiting"]
            if item["move"] == "verify"]


def _agent_for(reviewer: str) -> str:
    r"""The sub-agent TYPE to spawn, which is not the same thing as the card's reviewer.

    It was, and the message came out saying `spawn a \`peer\` sub-agent` — there is no such
    agent. `peer` and `human` are POLICIES about who may close a card; only a registered
    specialist is a name you can spawn. A live session read that line, ignored it, and spawned
    the right thing anyway, which is luck rather than design: this is the fifth time an
    instruction has named something that does not exist, and every previous one cost a run.
    """
    return reviewer if reviewer and reviewer not in POLICIES else "taskops-verifier"


def verify_text(rows: list[dict[str, Any]], *, closing: bool) -> str:
    """The message IS the fix: the sub-agent type and the card id, ready to spawn.

    `closing` shifts the framing rather than the content. At SubagentStop the session is mid-
    flow and the line is an instruction; at Stop it is the last thing between a card and a
    week of silence, so it says what the silence would cost.

    ONE path, and that is the fix. It used to end with "if you are the one reviewing, close it
    yourself" — telling a session to delegate and offering it the inline route in the same
    breath. A live session quoted both lines back at itself and took both: it spawned the
    verifier AND read the diff, and the verifier closed the card first, so the orchestrator's
    work was thrown away. An instruction with two doors is an instruction that opens both.
    """
    head = ("Before this turn ends — these cards are finished and unverified. A review nobody "
            "picks up is a card that reads as active for a week:" if closing else
            "Your worker handed this over. Nothing else will pick it up:")
    lines = [head]
    for row in rows:
        task = row["task"]
        lines.append(f"- {task['id']} “{task['title']}”")
        lines.append(f"    spawn a `{_agent_for(task['reviewer'])}` sub-agent for it, and tell "
                     f"it the card id — it claims and closes the card itself.")
    lines.append("Spawn it — do not read the diff yourself. You already have the worker's "
                 "summary in this context, so you are the one reader who cannot judge it "
                 "cold; the sub-agent starts empty and that is the whole of its value.")
    return "\n".join(lines)
