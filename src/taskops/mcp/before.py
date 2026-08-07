"""The sections that go ABOVE the spec — everything that changes what you do
before you start.

Split out of `dossier.py` along the line that module's own docstring draws: an
agent reads top-down and may stop early, so this is the part it must not miss.
Keeping it together also keeps the ORDER visible in one screen, which is the
thing `tests/test_mcp.py` pins and the thing v1 got wrong by burying a
collision warning under a long spec.

    rules       what holds for every card of this chapter
    collisions  who is in the same FILES, and the line to reach them
    elsewhere   who is working right now, on what
    resume      where the last worker stopped
    epic        what this card is PART OF
"""

from __future__ import annotations

from typing import Any

from .._json import as_rows, as_object, as_strings

# The room, not the board: this rides inside a take, above the spec.
ELSEWHERE_SHOWN = 6


def rules(data: dict[str, Any]) -> list[str]:
    """The chapter's half of the spec. Above the card's own spec on purpose:
    a rule you read after building is a rewrite.

    The chapter's `criteria` travel with them: a worker whose card is green
    while the milestone is not (docs/fan-out.md §4) never saw what the whole
    would be judged against."""
    stone = as_object(data.get("milestone"))
    out: list[str] = []
    lines = as_strings(stone.get("rules"))
    if lines:
        out += [
            "## Rules of this milestone — they hold for every card in it",
            "",
            *[f"- {line}" for line in lines],
            "",
        ]
    goals = as_strings(stone.get("criteria"))
    if goals:
        out += [
            "## The milestone is accepted against — your card is one piece of this",
            "",
            *[f"{n}. {line}" for n, line in enumerate(goals, 1)],
            "",
        ]
    return out


def review(data: dict[str, Any]) -> list[str]:
    """Where the card stands with its reviewer — ABOVE the spec, because a
    `changes` verdict changes what you do before you start: you fix, you do not
    rebuild. The note travels verbatim; a summary is where context goes to die."""
    stood = as_object(data.get("standing"))
    if not stood:
        return []
    verdict = str(stood.get("verdict", ""))
    if verdict == "changes":
        return [
            "## ⟳ Changes requested by the reviewer",
            "",
            f"> {stood.get('note')}",
            "",
            f"_by {stood.get('verdict_by')} — fix it, commit, then hand it in again: "
            'status=review note="…"._',
            "",
        ]
    if verdict == "pass":
        return [f"## ✓ Review passed ({stood.get('verdict_by')}) — the orchestrator closes it", ""]
    return [f"## Handed in by {stood.get('submitted_by')} — awaiting a verdict", ""]


def collisions(data: dict[str, Any]) -> list[str]:
    """Who else is in these files — and what to do about it.

    It ends with the action rather than the observation: told only that somebody
    else is in the file, an agent proceeds anyway.
    """
    others = as_rows(data.get("collisions"))
    if not others:
        return []
    lines = [
        f"- {', '.join(as_strings(o.get('files')))} — {o.get('id')} {o.get('title')} "
        f"({o.get('holder') or 'assigned'})"
        for o in others
    ]
    # The exact call, addressed to the actual holder. Told only to "say
    # something", an agent proceeds anyway; given the line to send, it sends it.
    first = others[0]
    who = first.get("holder") or ""
    reach = f'taskops_comment task={first.get("id")} text="…"' + (
        f' mentions=["{who}"]' if who else ""
    )
    return [
        "## ⚠ Also touching these files",
        "",
        *lines,
        "",
        "_A warning, not a lock: you each have your own worktree, so the worst case is a "
        "merge conflict. You do not own that card and do not need to — writing on it is "
        "always allowed, and it reaches them on their very next call:_",
        "",
        f"    {reach}",
        "",
    ]


def elsewhere(data: dict[str, Any]) -> list[str]:
    """The room right now. Not a duty to read — a map, so an agent that needs
    somebody knows they exist without spending a call to find out."""
    rows = as_rows(data.get("elsewhere"))
    if not rows:
        return []
    shown = rows[:ELSEWHERE_SHOWN]
    lines = [f"- {r.get('holder')} — {r.get('id')} {r.get('title')}" for r in shown]
    if len(rows) > len(shown):
        lines.append(f"- …and {len(rows) - len(shown)} more (taskops_board for all of them)")
    return ["## Working right now", "", *lines, ""]


def resume(data: dict[str, Any]) -> list[str]:
    if not data.get("resume"):
        return []
    return [
        "## Resume — where the last worker stopped",
        "",
        f"> {data['resume']}",
        "",
        "_Start from there, not from zero._",
        "",
    ]


def epic(data: dict[str, Any]) -> list[str]:
    """What this card is PART OF, resolved — the sentence that makes the spec
    make sense. A subtask read without it gets solved correctly for the wrong
    problem."""
    parent = as_object(data.get("epic"))
    if not parent:
        return []
    body = [f"## Part of {parent.get('id')} — {parent.get('title')} ({parent.get('status')})", ""]
    if parent.get("spec"):
        body += [f"_{parent['spec']}_", ""]
    return body
