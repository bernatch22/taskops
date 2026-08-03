"""`taskops context` — what the PROJECT and its chapter have settled. Bare, it shows the slice.

Two nouns where there was one, and the seam is whose fact it is: this one states the project's and
the chapter's, `taskops me` states yours. `--mine` and `--owner` are gone with the split — see
`me.py` for why a flag that decides what a verb IS was the wrong shape.

`objective` is gone from HERE and not from the model: an objective belongs to one dev, so it lives
on `taskops me`, and the project's north is a MILESTONE now — a chapter a person closes rather
than a sentence a newer sentence silently replaced.

`--project` is the LIFETIME. Without it a fact belongs to the chapter in force and leaves every
slice when that chapter is reached; with it, it stands forever. The default falls on the
recoverable side: a fact that died with its chapter is restated in one command, and one that lives
forever accumulates until nobody reads any of them.
"""

from __future__ import annotations

import argparse

from ....contracts.context import Fact
from ....render.context import render_context
from ....usecases._contextviews import context_for, context_of, history, show
from ....usecases.context import retire, state
from ._shared import add_actor, add_target, repo_of

__all__ = ["register", "run", "fact_line", "scoped"]

STATES = ("rule", "decision", "note")
"""What a person may state at project or chapter level. `objective` is not here — it is always
somebody's, so it is `taskops me objective`, and typing it here is refused by argparse naming it."""

GONE = {"objective": "taskops me objective", "show": "taskops context (bare)"}
"""Retired forms, named with their replacement. argparse's own refusal lists the choices and not
where the verb went, and a reader who typed the old spelling is asking exactly that."""


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("context", help="the rules, decisions and notes in force")
    add_target(parser)
    add_actor(parser)
    parser.add_argument("verb", nargs="?", default="", choices=("", *STATES, "log", "retire",
                                                                *GONE))
    parser.add_argument("text", nargs="?", default="",
                        help="the fact to state, or the id to retire")
    parser.add_argument("--labels", default="", help="comma-separated scope for a decision")
    parser.add_argument("--files", default="", help="comma-separated edit surface")
    parser.add_argument("--project", action="store_true",
                        help="it outlives the milestone — a standing rule, not this chapter's")
    parser.add_argument("--task", default="", help="the slice ONE card was handed")
    parser.add_argument("--milestone", default="", help="what one chapter settled, closed ones too")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    where, who = repo_of(args), str(args.actor)
    if args.verb in GONE:
        return f"`context {args.verb}` is now `{GONE[args.verb]}`"
    if args.verb == "log":
        return "\n".join(fact_line(f) for f in history(where)) or "nothing stated yet"
    if args.verb == "retire":
        return f"retired {retire(where, str(args.text), actor=who)['id']}"
    if args.verb in STATES:
        labels, files = scoped(args)
        stated = state(where, str(args.verb), str(args.text), labels=labels, files=files,
                       level="project" if args.project else "milestone", actor=who)
        return f"stated {fact_line(stated)}"
    return render_context(_read(args, where, who))


def _read(args: argparse.Namespace, where: str, who: str) -> "dict":  # type: ignore[type-arg]
    """One card's slice, one chapter's record, or what is in force. Three questions, one renderer:
    a slice read three ways that printed three ways is how two surfaces came to disagree."""
    if args.task:
        return dict(context_for(where, str(args.task)))
    if args.milestone:
        return dict(context_of(where, str(args.milestone)))
    return dict(show(where, actor=who))


def scoped(args: argparse.Namespace) -> tuple[list[str], list[str]]:
    """`--labels` and `--files`, split. Shared with `taskops me` so one comma means one thing."""
    return _list(args.labels), _list(args.files)


def _list(raw: str) -> list[str]:
    return [part.strip() for part in str(raw).split(",") if part.strip()]


def fact_line(fact: Fact) -> str:
    """One fact as a line — for `log` and for the receipt after a write, neither of which is a
    slice. The id truncated to eight because that is what `context retire` takes."""
    scope = ", ".join(fact["labels"] + fact["files"])
    tail = f"  [{scope}]" if scope else ""
    return f"{'~' if fact['retired'] else '·'} {fact['id'][:8]}  {fact['text']}{tail}"
