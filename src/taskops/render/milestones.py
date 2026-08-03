"""Chapters as text — the shape both a terminal and an agent read.

Pure, like everything here: values in, a string out. That is what lets `taskops milestone` and
`taskops_milestone` share one format instead of each growing its own — and it is why a change to
how a chapter reads is a change in one file rather than in two surfaces that drift.

**The counts are the point.** A milestone is a todo-list only if "how far along is it" is a number,
and a number nobody prints is a claim. `9 cards · 3 done · 2 in review` is one line and it is the
difference between a chapter and a slogan.
"""

from __future__ import annotations

from typing import Any

from ..contracts.milestone import Milestone

__all__ = ["render_chapter", "render_chapters", "count_line"]

MARK = {"planned": "○", "in_force": "◆", "review": "◐", "reached": "✓", "abandoned": "—"}
"""One glyph per state, matching the card marks in `render/_text.py` in spirit: a reader who has
learned the board's vocabulary must not have to learn a second one for chapters."""

SHOWN = 8
"""Cards listed before it stops. A chapter of forty must not answer with forty lines — the caller
asked which chapter, and `taskops tasks list --milestone` is the question about its cards."""


def count_line(counts: dict[str, int]) -> str:
    """`9 cards · 3 done · 2 in review`, or "" for a chapter with none yet.

    `cancelled` is named rather than folded into the total, because "3 of 9 done" and "3 of 9 done,
    1 withdrawn" are two different sentences and only one of them is true.
    """
    total = counts.get("total", 0)
    if not total:
        return ""
    said = [f"{total} card(s)"]
    for status, label in (("done", "done"), ("review", "in review"), ("ready", "ready"),
                          ("blocked", "blocked"), ("cancelled", "withdrawn")):
        if counts.get(status):
            said.append(f"{counts[status]} {label}")
    return " · ".join(said)


def render_chapter(chapter: Milestone, counts: dict[str, int], *,
                   cards: list[dict[str, Any]]) -> str:
    """One chapter, with its cards when the caller asked for them.

    A chapter in `review` says what it is waiting for, because that is the one state where a
    session must not start new work under it — and saying "review" without saying who has to act
    would leave a reader to infer the one thing that matters.
    """
    head = f"{MARK.get(chapter['state'], '·')} {chapter['id'][:8]}  {chapter['title']}"
    lines = [head + (f"  by {chapter['horizon']}" if chapter["horizon"] else "")]
    # The GOAL under the title, indented, and only when there is one. A chapter is a title somebody
    # can pick out of a list plus the outcome that says when it is over, and printing only the first
    # is how "El importador" ends up meaning four different things to four people.
    if chapter["goal"]:
        lines.append(f"   {chapter['goal']}")
    if said := count_line(counts):
        lines.append(f"   {said}")
    lines += _waiting(chapter)
    if cards:
        lines.append("")
        lines += [f"   {c['status']:<9} {c['id']}  {c['title'][:58]}" for c in cards[:SHOWN]]
        if len(cards) > SHOWN:
            lines.append(f"   … and {len(cards) - SHOWN} more")
    return "\n".join(lines)


def _waiting(chapter: Milestone) -> list[str]:
    """What a chapter's state asks of the reader, when it asks anything."""
    if chapter["state"] == "review":
        said = f" — “{chapter['note']}”" if chapter["note"] else ""
        return [f"   REPORTED FINISHED{said}",
                f"   A person verifies: `taskops milestone done {chapter['id'][:8]}` — or sends it "
                f"back with `reject`. Nothing new starts under it until then."]
    if chapter["state"] in ("reached", "abandoned"):
        by = chapter["closed_by"] or "nobody on record"
        return [f"   {chapter['state']} · {by}" + (f" — “{chapter['note']}”" if chapter["note"]
                                                   else "")]
    return []


def render_chapters(active: list[Milestone], planned: list[Milestone],
                    counts: dict[str, dict[str, int]]) -> str:
    """Every chapter being worked on, then what is next.

    Planned ones are TITLES and nothing else. "Where is this going" is a real question, and a
    chapter with no cards and no facts must not read as something to pick up — so it gets one line
    and no counts, which is exactly as much as it is.
    """
    if not active and not planned:
        # Both spellings, because this one string is printed by a terminal and by an MCP reply, and
        # naming only the tool sent a person to a command that does not exist.
        return ('no milestone yet — every card belongs to one, so `plan` will refuse until one is '
                'open.\n  a person:  taskops milestone new "<a short name>" '
                '--goal "<what done means>"'
                '\n  an agent:  taskops_milestone create="<a short name>" goal="<what done means>"')
    lines = [f"# active — {len(active)}"] if active else []
    for chapter in active:
        lines.append(render_chapter(chapter, counts.get(chapter["id"], {}), cards=[]))
    if planned:
        lines += ["", "# planned — written down, not started",
                  *[f"○ {p['id'][:8]}  {p['title']}" for p in planned]]
    return "\n".join(lines)
