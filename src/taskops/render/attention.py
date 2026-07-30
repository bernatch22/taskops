"""The sweep as text — grouped by move, because the move is what the reader does next.

Sorted by card would make a reader scan forty rows deciding which verb applies to each. Grouped
by verb, the same list is four short answers to "what do I do now", and the heading carries the
call that does it. Pure, like everything in this layer.
"""

from __future__ import annotations

from ..contracts.attention import MOVES, Attention, Waiting

__all__ = ["render_attention", "HEADINGS"]

HEADINGS: dict[str, str] = {
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
        return "nothing is waiting on a decision — every open card is being worked on."
    lines: list[str] = []
    for move in MOVES:
        group = [item for item in view["waiting"] if item["move"] == move]
        if not group:
            continue
        lines += ["", f"{HEADINGS[move]}  ({len(group)})"]
        lines += [_row(item) for item in group]
    return "\n".join(lines).strip("\n")


def _row(item: Waiting) -> str:
    """The id, the title, and the fact the move was derived from — never the group's own words.

    The `why` is what lets a reader disagree. A row that only repeated its heading would give a
    session nothing to check the verb against, and acting on an unchecked verb is how a card
    already being worked on gets dispatched a second time.
    """
    task = item["task"]
    return f"  {task['id']}  {task['title'][:52]:<52}  {item['why']}"
