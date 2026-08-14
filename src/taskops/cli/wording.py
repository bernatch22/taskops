"""What the delivery hook SAYS, and how it hands it to the host.

Split out of `claude.py` when it outgrew the 200-line budget, and split here
because the seam is real: that file is the mechanism (payload, reader, throttle,
one board round trip, exit 0) and this one is the output — the sentences and the
envelope they leave in. Nothing here reads the clock, the disk or the board, so
every line is testable as a string.

The wording is half the feature. This text is injected into a transcript that is
doing something else, so each line is: **the count, what is wrong, and the exact
call that clears it** — a reader mid-turn must be able to act without opening
anything. A line that makes somebody go look is noise, and noise is how a hook
gets deleted.

The three orchestrator lines come in the board's own ranking — merge, review,
stalled (`verbs/pulse.py`'s docstring) — and MENTIONS sits between merge and
review there, which is the order `lines()` assembles.
"""

from __future__ import annotations

import json
from typing import Any

SHOWN = 4
"""Ids per line. Enough to act on; past that the count is the fact and the
board is one call away."""

# id → sentence. `{n}` is the count, `{ids}` the (capped) list.
CALLS = {
    "merge": "◆ taskops: {n} done, not in the trunk — one taskops_merge task= each: {ids}",
    "review": (
        "◆ taskops: {n} handed in, nobody checking — review them yourself, in this"
        " session (taskops_review task= claims, verdict= judges): {ids}"
    ),
    "stalled": (
        "◆ taskops: {n} owned, nobody running them — taskops_assign tasks=[…]"
        " hands one over, then spawn the brief it returns: {ids}"
    ),
}


def lines(actor: str, mentions: list[dict[str, Any]], groups: dict[str, Any]) -> list[str]:
    """Everything to deliver this look, in the order the board ranks it."""
    out = _group("merge", groups)
    out += _mentions(actor, mentions)
    out += _group("review", groups)
    out += _group("stalled", groups)
    return out


def _mentions(actor: str, rows: list[dict[str, Any]]) -> list[str]:
    """One line per mention, naming the addressee rather than saying "you": the
    reader may be the orchestrator, and the card may have been resolved from a
    worktree path that belongs to somebody else."""
    return [
        f"✉ taskops: {row.get('by')} mentioned {actor} on {row.get('id')} "
        f"“{trim(row.get('text'))}” — reply on the card "
        f'(taskops_comment task={row.get("id")} text="…") and it clears.'
        for row in rows
    ]


def _group(name: str, groups: dict[str, Any]) -> list[str]:
    """Silence when the group is empty — which must stay the common case."""
    ids = [str(i) for i in groups.get(name, []) if i]
    if not ids:
        return []
    shown = " ".join(ids[:SHOWN]) + (f" +{len(ids) - SHOWN} more" if len(ids) > SHOWN else "")
    return [CALLS[name].format(n=len(ids), ids=shown)]


def trim(body: object) -> str:
    """A line, not the comment: the whole text is one taskops_card away, and
    this is injected into a transcript that is doing something else."""
    line = " ".join(str(body or "").split())
    return f"{line[:157]}…" if len(line) > 158 else line


def emit(event: str, context: str) -> None:
    """The contract verified against the Claude Code hooks reference: JSON on
    stdout is parsed only on exit 0, and `hookSpecificOutput.additionalContext`
    is wrapped in a system reminder and inserted where the hook fired.
    `hookEventName` must echo the event that fired, so it is taken from the
    payload rather than assumed — plain stdout reaches the transcript for
    `UserPromptSubmit` but is only logged for `PostToolUse`, so the JSON form is
    the only one that works for both."""
    print(
        json.dumps(
            {"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}},
            ensure_ascii=False,
        )
    )
