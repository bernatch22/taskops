"""The question `plan` asks back: who closes these?

Split from `results` on its budget, and the split reads true — that module renders WHAT a call
did, and this one asks something the caller has not decided yet.

**There is deliberately no project default.** A card's `reviewer` is written when the card is
created and the engine reads it at close time, so with nothing set a card comes out naming
nobody. That is the right default for the way taskops is first tried — one developer, nobody
else on the board, and a rule refusing every close would make the tool unusable — and it is the
wrong state for a card to stay in, because the only guard left is the weakest of the three: an
AGENT may not close the review it opened. A second agent of the same developer may, and so may
the developer.

So the plan result says so, per batch, once. **An instruction is not a mechanism** — that lesson
is carved into this codebase several times — and the corollary is that anything a model must act
on belongs in the message that needs it. A sentence in a guide is read once and gone by the
second compaction; this arrives in the return value of the call that created the cards, while
the planner still has the plan in its head and every id in front of it.
"""

from __future__ import annotations

from ..contracts import Task

__all__ = ["ask_who_reviews"]

SHOW = 4
"""Ids named before it stops listing. A plan of forty cards must not answer with forty lines —
the point is the QUESTION, and one `tasks edit` per card is not the answer anybody wants."""


def ask_who_reviews(created: list[Task]) -> str:
    """The ask, or "" when every card already says who closes it.

    Silent is the common case on a board that decided this once, and silence matters: a plan
    result that always ended in a paragraph about reviewers is a paragraph that stops being
    read, which is how the one time it mattered goes past unnoticed.
    """
    undecided = [task["id"] for task in created if not task["reviewer"].strip()]
    if not undecided:
        return ""
    named = ", ".join(undecided[:SHOW])
    more = f" (+{len(undecided) - SHOW} more)" if len(undecided) > SHOW else ""
    return "\n".join([
        f"⚠ {len(undecided)} card(s) name NO reviewer: {named}{more}",
        "  Nothing decides who may close them except the weakest rule — an agent may not close",
        "  the review it opened itself. Another agent of the same developer may, and so may that",
        "  developer. Decide it now, per card, while you still have the plan in your head:",
        "",
        "      taskops tasks edit <id> --reviewer peer       anybody but the author's own dev",
        "      taskops tasks edit <id> --reviewer human      a person; no agent may close it",
        "      taskops tasks edit <id> --reviewer dev:ana    that person, nobody else",
        "      taskops tasks edit <id> --reviewer none       deliberately unreviewed",
        "",
        "  Or pass `reviewer` on the plan entry next time, which is one call instead of N.",
    ])
