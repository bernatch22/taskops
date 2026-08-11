"""The brief: everything a sub-agent needs, in the message that spawns it.

Self-contained on purpose. In v1 the worker protocol arrived through a
SessionStart hook, an agent file and a channel — three copies that drifted, and
a worker that missed all three wandered into the pool as the human's identity.
Here it is one block of text, generated from the board it describes.
"""

from __future__ import annotations

from typing import Any

from . import render
from .._json import as_rows, as_object, as_strings


def briefs(data: dict[str, Any]) -> str:
    """One paste-ready brief per card. Self-contained: no hook tops it up later."""
    out: list[str] = []
    for brief in as_rows(data.get("briefs")):
        out += [
            f"## {brief['task']} — {brief['title']}  →  spawn one sub-agent with this:",
            *_apart(brief),
            "```",
            f'You are {brief["actor"]}. Card {brief["task"]}: "{brief["title"]}".',
            f"Pass actor={brief['actor']} on EVERY taskops call — you share the session's",
            "MCP server, and without it the board hears the orchestrator, not you.",
            f"export TASKOPS_ACTOR={brief['actor']}   # for the git hooks in your shell",
            f"cd {brief['worktree']}          # your world; branch {brief['branch']} is pinned to it",
            f"Milestone {brief.get('milestone', '')} — {brief.get('goal', '')}".rstrip(" —"),
            *_rules(brief),
            *_part_of(brief),
            *_criteria(brief),
            "",
            f"1. taskops_take task={brief['task']} actor={brief['actor']}   (the spec, thread and graph)",
            "2. implement it; commit in that directory",
            # A reviewed card is handed IN, never closed by its worker: the
            # brief is where the exit is named, or the first close attempt is a
            # refusal the worker has to decode mid-flight.
            (
                f'3. taskops_update task={brief["task"]} actor={brief["actor"]} status=review note="<what you did>"'
                "   — this card needs REVIEW: hand it in, stay reachable; a reviewer answers on the card"
                if brief.get("review")
                else f'3. taskops_update task={brief["task"]} actor={brief["actor"]} status=done note="<what you did>"'
            ),
            'Stuck or out of context → status=released note="got as far as X".',
            "Never: git switch, merge, push to main, or edit another card's directory.",
            "```",
        ]
        if brief.get("labels"):
            out += ["> labels: " + " ".join(f"#{x}" for x in as_strings(brief.get("labels")))]
        if brief.get("displaced"):
            # Said out loud because the worktree may not be empty: whoever held
            # this was working in it, and stopped mid-sentence rather than at a
            # commit. `git status` there before the first edit, not after.
            out += [
                f"> ⚠ handed over from {brief['displaced']}, whose lease was still live — "
                "check `git status` in the worktree for work it left uncommitted"
            ]
        if brief.get("resume"):
            out += [f"> it was released before: {brief['resume']}"]
        if as_rows(brief.get("collisions")):
            names = ", ".join(c["id"] for c in as_rows(brief.get("collisions")))
            out += [f"> ⚠ shares files with {names}"]
        out.append("")
    out.append(render.pulse(data))
    return "\n".join(out)


def _apart(brief: dict[str, Any]) -> list[str]:
    """The wave held these two apart and the orchestrator dispatched them anyway.

    A SENTENCE, in the header, above the fold — not a refusal: the whole chapter
    rests on "a warning is never a lock" (`core/seams.py`), and the assign has
    already been written by the time this renders. It is here rather than only in
    the board's TAKE listing because the duplicated-helper failures it names were
    all discovered inside a worker, and this is the one text a worker reads first.
    """
    why = as_object(brief.get("apart"))
    if not why:
        return []
    shared = as_strings(why.get("files")) or as_strings(why.get("terms"))
    verb = "the same files" if why.get("files") else "the same concept"
    return [
        f"> ⚠ the wave holds this apart from {why.get('with')}: {verb} — "
        f"{', '.join(shared)}. Land the seam serialized first, or expect two of it "
        "Dispatching anyway is your call; nothing is blocked."
    ]


def _rules(brief: dict[str, Any]) -> list[str]:
    """The chapter's rules, in the brief AND in the take. Duplicated on purpose:
    the brief is what spawns the agent, and a rule it only meets after its first
    edit is a rewrite."""
    lines = as_strings(brief.get("rules"))
    if not lines:
        return []
    return ["Rules of this milestone — they hold whatever you are building:",
            *[f"  · {line}" for line in lines]]


def _part_of(brief: dict[str, Any]) -> list[str]:
    """The epic, by name, inside the brief — a worker should not have to call
    anything to learn what the thing it is building is FOR."""
    epic = as_object(brief.get("epic"))
    return [f"Part of {epic['id']} — {epic['title']}"] if epic else []


def _criteria(brief: dict[str, Any]) -> list[str]:
    criteria = as_strings(brief.get("criteria"))
    if not criteria:
        return []
    return ["", "Accepted against:", *[f"  {n}. {line}" for n, line in enumerate(criteria, 1)]]
