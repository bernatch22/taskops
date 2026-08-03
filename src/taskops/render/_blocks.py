"""A slice as blocks — the four a session reads, in the order the order argues for.

Split out of `context.py` and `opening.py` because both render the same thing and neither may own
it: the CLI's `context show`, the MCP reply and the SessionStart injection are three surfaces of
one slice, and the last time each formatted its own they disagreed about what was in force.

**The order is the argument.** What is true regardless of the work comes before the work:

1. the project's RULES — every card, every chapter, no exceptions;
2. the settings the engine enforces (rendered by `opening`, which is where policies arrive);
3. the MILESTONE in force, with its counts and its own facts under it;
4. what is waiting on a person.

A reader who learns the chapter before the rules judges the rules by the chapter, which is
backwards: a chapter is what we are doing now and a rule is what holds whatever we do.
"""

from __future__ import annotations

from ..contracts.context import Fact
from ..contracts.milestone import Milestone
from ..contracts.slice import ContextSlice
from .milestones import MARK, count_line

__all__ = ["project_block", "chapters_block", "fact_line", "dev"]

NO_CHAPTER = [
    "## No milestone — the board has no chapter open",
    "Every card belongs to one, so `taskops_plan` will REFUSE until there is one. Open it with",
    '`taskops_milestone create="<what this is for>"` — a sentence a person would recognise as',
    "finished, not a task.",
]
"""Named here rather than left to a caller because a session must learn this from the OPENING and
not from the refusal. A refusal mid-plan costs a turn and reads as a bug in the tool."""


def project_block(view: ContextSlice) -> list[str]:
    """The project's own facts: rules first, then scoped decisions. Empty when it has stated none.

    Omitted rather than printed as "(none)": a heading over nothing teaches a reader that this
    board does not use rules, which is a different claim from "nobody has written one yet" — and
    on the injection it is four lines every session pays for to learn nothing.
    """
    rules, decisions = view["project_rules"], view["project_decisions"]
    if not rules and not decisions:
        return []
    lines = ["## Rules — the project's. Every card, every milestone, no exceptions."]
    lines += [fact_line(f) for f in rules]
    lines += [fact_line(f) for f in decisions]
    return [*lines, ""]


def chapters_block(view: ContextSlice) -> list[str]:
    """The chapter, or every active one, or the block that says there is none.

    Three shapes because the slice has three readers. A CARD's slice carries `milestone` and an
    empty `active` — one chapter, its own, which is the whole point of narrowing. The OVERVIEW
    carries `active` and no `milestone`, because several are being worked on at once and the
    orchestrator is the reader that chooses between them. A board with neither is a board that
    cannot plan, and that is the one case worth four lines.
    """
    if view["milestone"]:
        return [*_chapter(view, view["milestone"]), ""]
    if not view["active"]:
        return [*NO_CHAPTER, ""]
    lines: list[str] = []
    for chapter in view["active"]:
        if lines:
            lines.append("")                    # several at once: one blank between chapters
        lines += _chapter(view, chapter)
    if view["planned"]:
        lines.append("   next        " + " · ".join(p["text"] for p in view["planned"]))
    return [*lines, ""]


def _chapter(view: ContextSlice, chapter: Milestone) -> list[str]:
    """One chapter and the facts filed under IT, indented so the nesting is the model.

    Filtered by chapter and not simply printed, because several are active at once: a decision
    taken while doing the importer must not read as governing the billing chapter too. A fact with
    no `milestone` shows under every one — that is a fact from a board written before chapters
    existed, and the alternative is hiding it everywhere.
    """
    lines = [_head(chapter), f"   {said}" if (said := count_line(view["counts"].get(chapter["id"],
                                                                                   {}))) else ""]
    for label, facts in (("rules", view["rules"]), ("decisions", view["decisions"]),
                         ("notes", view["notes"])):
        under = [f for f in facts if not f["milestone"] or f["milestone"] == chapter["id"]]
        lines += [f"   {label if i == 0 else '':<11} {_said(f)}" for i, f in enumerate(under)]
    if (goal := view["yours"]) and (not goal["milestone"] or goal["milestone"] == chapter["id"]):
        lines.append(f"   {'yours':<11} {_said(goal)}")
    return [line for line in lines if line]


def _head(chapter: Milestone) -> str:
    """`review` gets its own heading, because a session must not start new work under a chapter a
    person has been asked to close — and "review" in a status field is not that sentence."""
    if chapter["state"] == "review":
        said = f" — “{chapter['note']}”" if chapter["note"] else ""
        return (f"## Milestone COMPLETED, waiting for a person — {chapter['text']}\n"
                f"   Reported finished{said}\n"
                f"   → verify: `taskops milestone done {chapter['id'][:8]}`  ·  send back: "
                f"`taskops milestone reject {chapter['id'][:8]} -m \"…\"`\n"
                f"   Nothing new starts under it until a person closes or returns it.")
    by = f"      by {chapter['horizon']}" if chapter["horizon"] else ""
    return f"## {MARK.get(chapter['state'], '·')} Milestone in force — {chapter['text']}{by}"


def fact_line(fact: Fact) -> str:
    """The id first and truncated to eight: it is what `context retire` takes, and a full
    event hash on every line would push the text — the part anybody reads — off the screen."""
    return f"{'~' if fact['retired'] else '·'} {_said(fact)}"


def _said(fact: Fact) -> str:
    scope = ", ".join(fact["labels"] + fact["files"])
    tail = f"  [{scope}]" if scope else ""
    if fact["horizon"]:
        tail += f"  by {fact['horizon']}"
    return f"{fact['id'][:8]}  {fact['text']}{tail}"


def dev(owner: str) -> str:
    return owner.partition(":")[2] or owner
