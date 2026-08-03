"""`taskops_context` — the one tool that both reads the standing facts and states them.

Its own module because it is the only one of its kind: every other tool on this surface either
reads or writes, and this one does both because they are one question asked in two directions.
Splitting it into `taskops_context` and `taskops_context_state` would cost every connected
agent a second description to serve a caller that almost always only reads.

**The write half is not fenced HERE.** The refusal for a worker lives in `usecases.context`,
where `Bash` cannot walk around it — a guard in a transport is a guard the other two do not
have, and leaving the write off this surface is exactly what used to pass for the rule.
"""

from __future__ import annotations

from typing import Any

from ...render import render_context
from ...usecases import context_for, context_retire, context_show, context_state
from . import arguments as arg

__all__ = ["context_"]


def context_(args: dict[str, Any]) -> str:
    """Read what is in force, read one card's slice, state a fact, or withdraw one.

    Four shapes, and they cannot overlap: `retire` takes one back, `state`+`text` records one,
    `task` narrows the read to a card, and none of those means "show me everything" — which is
    what is left.
    """
    where, who = arg.repo(args), arg.optional(args, "actor")
    if gone := arg.optional(args, "retire"):
        return f"retired {context_retire(where, gone, actor=who)['id'][:8]}"
    if sort := arg.optional(args, "state"):
        said = context_state(where, sort, arg.text(args, "text"),
                             labels=arg.csv(args, "labels"),
                             owner=who if arg.flag(args, "mine") else "", actor=who)
        return f"stated {said['sort']} {said['id'][:8]}: {said['text']}"
    wanted = arg.optional(args, "task")
    if wanted:
        return render_context(context_for(where, wanted))
    # `mine` narrows the READ too: the overview answers "who is on what", your page answers
    # "what am I under". Two questions, and the same flag says which one was asked.
    return render_context(context_show(where, actor=who, mine=arg.flag(args, "mine")))
