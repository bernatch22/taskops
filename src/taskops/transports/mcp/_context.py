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
from ...usecases._contextviews import context_of
from . import arguments as arg

__all__ = ["context_"]


def context_(args: dict[str, Any]) -> str:
    """Read what applies, read one card's slice, read a chapter, state a fact, or withdraw one.

    Five shapes and they cannot overlap: `retire` takes one back, `state`+`text` records one,
    `task` narrows the read to a card, `milestone` narrows it to a chapter, and none of those
    means "show me everything" — which is what is left.
    """
    where, who = arg.repo(args), arg.optional(args, "actor")
    if gone := arg.optional(args, "retire"):
        return f"retired {context_retire(where, gone, actor=who)['id'][:8]}"
    if sort := arg.optional(args, "state"):
        return _stated(where, sort, args, who)
    if wanted := arg.optional(args, "task"):
        return render_context(context_for(where, wanted))
    if chapter := arg.optional(args, "milestone"):
        return render_context(context_of(where, chapter))
    # The reader's own page: the project's facts, the chapters', and theirs. NOT the overview —
    # `mine` used to choose between them and it is gone, because a flag that could file a fact as
    # the PROJECT's is the flag that erased the team's north twice. An agent asking what applies
    # is asking about itself; "who is on what" is a board question and the board has a screen.
    return render_context(context_show(where, actor=who, mine=True))


def _stated(where: Any, sort: str, args: dict[str, Any], who: str) -> str:
    """One fact, recorded. `objective` is the caller's OWN and every other sort is the project's
    or the chapter's — which is the whole of what `mine` used to say, now said by the sort.

    `level` is the LIFETIME: `project` outlives every chapter, and anything else belongs to the
    one in force. The default is the chapter, deliberately — a fact that dies with it is recovered
    by restating it, and one that lives forever accumulates in silence.
    """
    said = context_state(where, sort, arg.text(args, "text"),
                         labels=arg.csv(args, "labels"),
                         level=arg.optional(args, "level") or "milestone",
                         owner=who if sort == "objective" else "", actor=who)
    where_it_lives = "the project" if said["level"] == "project" else "this chapter"
    return f"stated {said['sort']} {said['id'][:8]} in {where_it_lives}: {said['text']}"
