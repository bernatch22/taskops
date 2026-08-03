"""`taskops context` — the standing facts a worker needs and its card cannot carry.

The verbs read as sentences (`context objective "ship 0.4 by Friday"`) because the caller is
usually an agent composing a command from a sentence a human said. `show` is the default: the
question asked most often is "what am I working under right now".

The SLICE is rendered by `render.render_context` and not here. It was rendered here too, and
the two copies drifted the moment one grew a section: the package one learned to show each
dev's objective and this one did not, so the same slice read differently depending on which
door you came in. `_line` stays, because `log` and the receipt after a `state` are one fact
each and not a slice.
"""

from __future__ import annotations

import argparse

from ....contracts.context import SORTS, Fact
from ....render import render_context
from ....usecases._contextviews import context_for, history, show
from ....usecases._routing import whoami
from ....usecases.context import retire, state
from ._shared import add_actor, add_target, repo_of

__all__ = ["register", "run"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("context", help="the standing objective, invariants and decisions")
    add_target(parser)
    add_actor(parser)
    parser.add_argument("verb", nargs="?", default="show",
                        choices=("show", *SORTS, "log", "retire"))
    parser.add_argument("text", nargs="?", default="",
                        help="the fact to state, or the id to retire")
    parser.add_argument("--labels", default="", help="comma-separated scope for a decision")
    parser.add_argument("--files", default="", help="comma-separated edit surface")
    parser.add_argument("--horizon", default="", help="when an objective expires")
    parser.add_argument("--owner", default="", help="whose fact this is: `dev:<name>`")
    parser.add_argument("--mine", action="store_true",
                        help="with a sort: file it under YOU. With show: your page, not the "
                             "overview")
    parser.add_argument("--task", default="", help="with show: the slice for one card")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    where, who = repo_of(args), str(args.actor)
    if args.verb == "log":
        return "\n".join(_line(f) for f in history(where)) or "nothing stated yet"
    if args.verb == "retire":
        return f"retired {retire(where, str(args.text), actor=who)['id']}"
    if args.verb in SORTS:
        return f"stated {_line(_state(args, who))}"
    return render_context(context_for(where, str(args.task)) if args.task
                          else show(where, actor=who, mine=bool(args.mine)))


def _state(args: argparse.Namespace, who: str) -> Fact:
    # `--mine` files it under the caller as a FULL actor id. Two bugs live here, both found by
    # running it: the first version fell back to the literal string "me" when `--actor` was
    # absent, and the second passed the bare dev name. Neither parses, so both read as NO owner
    # — the fact was stored as the PROJECT's and, being newer, erased the team's objective from
    # every slice. Silently, until `state` learned to refuse an owner it cannot parse.
    owner = str(args.owner) or (whoami(repo_of(args), str(args.actor)) if args.mine else "")
    return state(repo_of(args), str(args.verb), str(args.text), labels=_list(args.labels),
                 files=_list(args.files), horizon=str(args.horizon), owner=owner, actor=who)


def _list(raw: str) -> list[str]:
    return [part.strip() for part in str(raw).split(",") if part.strip()]


def _line(fact: Fact) -> str:
    scope = ", ".join(fact["labels"] + fact["files"])
    tail = f"  [{scope}]" if scope else ""
    return f"{'~' if fact['retired'] else '·'} {fact['id'][:8]}  {fact['text']}{tail}"
