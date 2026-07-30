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

from .attention import attention

__all__ = ["unverified", "verify_text"]


def unverified(start: Path | str) -> list[dict[str, Any]]:
    """Every card sitting in `review` with nobody verifying it.

    Derived from `attention` rather than queried again, so there is one definition of "waiting
    for a verifier" and a board that disagrees with the sweep is impossible by construction.
    """
    return [item for item in attention(start)["waiting"] if item["move"] == "verify"]


def verify_text(rows: list[dict[str, Any]], *, closing: bool) -> str:
    """The message IS the fix: the sub-agent type and the card id, ready to spawn.

    `closing` shifts the framing rather than the content. At SubagentStop the session is mid-
    flow and the line is an instruction; at Stop it is the last thing between a card and a
    week of silence, so it says what the silence would cost.
    """
    head = ("Before this turn ends — these cards are finished and unverified. A review nobody "
            "picks up is a card that reads as active for a week:" if closing else
            "Your worker handed this over. Nothing else will pick it up:")
    lines = [head]
    for row in rows:
        task = row["task"]
        lines.append(f"- {task['id']} “{task['title']}”")
        lines.append(f"    spawn a `{task['reviewer'] or 'taskops-verifier'}` sub-agent for it, "
                     f"and tell it the card id — it claims and closes the card itself.")
    lines.append("If you are the one reviewing, read the diff and close it yourself with "
                 "`taskops_update status=done` and evidence per criterion.")
    return "\n".join(lines)
