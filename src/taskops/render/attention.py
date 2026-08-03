"""The sweep as text — grouped by move, because the move is what the reader does next.

Sorted by card would make a reader scan forty rows deciding which verb applies to each. Grouped
by verb, the same list is four short answers to "what do I do now", and the heading carries the
call that does it. Pure, like everything in this layer.
"""

from __future__ import annotations

from ..contracts.attention import MOVES, Attention, Waiting
from ..contracts.milestone import Milestone

__all__ = ["render_attention", "HEADINGS"]

HEADINGS: dict[str, str] = {
    "land": "LAND — done and NOT in the trunk. Spawn `taskops-worker` on each; it resolves "
            "the conflict and merges. `taskops land <id>` retries once it is clean",
    "verify": "VERIFY — hand each to the verifier; a close here may unblock others",
    "resume": "RESUME — spawn the worker each is assigned to, or release the card",
    "dispatch": "DISPATCH — `taskops_dispatch tasks=…`, then spawn one worker per brief",
    "specless": "NEEDS A SPEC — a person writes it; a worker handed one of these guesses",
    "stalled": "PARKED — nothing ever unblocks these on its own; unblock, re-plan or cancel",
}
"""One line per group, and each names the ACTION rather than the condition. A sweep whose
headings said "in review" and "assigned" would be a board dump; what a session needs from it is
the verb, and the two orderings differ — `verify` leads because finishing beats starting."""


def render_attention(view: Attention) -> str:
    if view["quiet"]:
        return ("nothing is waiting on a decision — every open card is being worked on.\n"
                "To be woken when that changes: run `taskops attention --wait` in the "
                "background and keep working; when it returns, sweep again.")
    lines: list[str] = _mail(view.get("mail", 0)) + _confirm(view.get("confirm") or [])
    for move in MOVES:
        group = [item for item in view["waiting"] if item["move"] == move]
        if not group:
            continue
        lines += ["", f"{HEADINGS[move]}  ({len(group)})"]
        lines += [_row(item) for item in group]
    return "\n".join(lines).strip("\n")


def _mail(mail: int) -> list[str]:
    """Messages addressed to this actor, FIRST — above every card group.

    Somebody chose you for this: a routed review, a question, a mention. Everything below it in
    the sweep is derived from state and will still be there next time; a message is the only
    line that exists because a person or another agent decided you specifically should see it.
    """
    if not mail:
        return []
    return [f"ADDRESSED TO YOU — {mail} message(s). `taskops ask` reads them, and they are the "
            f"only lines here nobody else is also being shown"]


def _confirm(chapters: list[Milestone]) -> list[str]:
    """Milestones reported finished, above every card group.

    Above them because it is the biggest thing on the list and the one nothing else unblocks: no
    count of closed cards can mean "we shipped it", so until a person says so the chapter stays
    open and nothing new starts under it. Both ways out are named — a sweep that only said
    "waiting" would leave a reader to guess whether they were meant to verify or to reject.
    """
    if not chapters:
        return []
    lines = ["CONFIRM — a milestone was reported finished and waits for a PERSON"]
    for chapter in chapters:
        said = f" — “{chapter['note']}”" if chapter["note"] else ""
        lines.append(f"  {chapter['id'][:8]}  {chapter['text'][:52]:<52}{said}")
        lines.append(f"            → `taskops milestone done {chapter['id'][:8]}`  ·  send back: "
                     f"`taskops milestone reject {chapter['id'][:8]} -m \"…\"`")
    return lines


def _row(item: Waiting) -> str:
    """The id, the title, and the fact the move was derived from — never the group's own words.

    The `why` is what lets a reader disagree. A row that only repeated its heading would give a
    session nothing to check the verb against, and acting on an unchecked verb is how a card
    already being worked on gets dispatched a second time.
    """
    task = item["task"]
    return f"  {task['id']}  {task['title'][:52]:<52}  {item['why']}"
