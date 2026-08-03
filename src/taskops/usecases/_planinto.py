"""Which chapter a new card lands in — the refusal that makes the model true.

**Every card belongs to exactly one milestone.** That is what turns a chapter into a todo-list
(its cards ARE its items, so "how far along" is a count) and it is what BOUNDS a worker's slice
(the facts it reads are its own card's chapter's, one of them, whatever number are active).

An invariant with no guard is a sentence in a document. So this refuses rather than guesses, in
both directions where guessing would be wrong — and each refusal names the way out, because this
project has paid four debugging sessions for refusals that only said no.
"""

from __future__ import annotations

from typing import Any

from .._errors import BadRequest
from ..storage import Store
from ..storage.milestone import active, one

__all__ = ["chapter_to_plan_into"]


def chapter_to_plan_into(store: Store, entries: list[dict[str, Any]]) -> str:
    """The milestone every card in this batch joins.

    ONE for the whole batch, not one per entry: a `plan` call is a decomposition of a single piece
    of work, and a tree whose branches belonged to different chapters would be a tree whose parts
    are judged against different rules.
    """
    asked = {str(e.get("milestone") or "").strip() for e in entries} - {""}
    if len(asked) > 1:
        raise BadRequest("these entries name different milestones — one `plan` call is one "
                         "decomposition, and a tree split across chapters is a tree whose "
                         "branches are judged against different rules. Plan them separately.")
    running = active(store)
    if asked:
        wanted = asked.pop()
        if (found := one(store, wanted)) is None:
            raise BadRequest(f"`{wanted}` names no milestone — `taskops milestone list` prints "
                             f"them with the eight characters that name one")
        return found["id"]
    if not running:
        raise BadRequest(
            "this board has no milestone, and every card belongs to one — that is what makes a "
            "chapter a todo-list instead of a slogan, and what keeps a worker's context from "
            "growing forever.\n"
            '  open one:  taskops milestone new "<what this is for>" --horizon YYYY-MM-DD\n'
            "  or from an agent:  taskops_milestone create=\"<what this is for>\"")
    if len(running) > 1:
        listed = "\n".join(f"    {m['id'][:8]}  {m['title'][:60]}" for m in running)
        raise BadRequest(
            f"{len(running)} milestones are active, so which one these cards belong to is not "
            f"something to guess — a card in the wrong chapter is judged against somebody else's "
            f"rules and nothing says so.\n{listed}\n"
            f"  name one:  `milestone` on the entry, or `--milestone <id>`")
    return running[0]["id"]
