"""`taskops me` — your own page: what you are chasing, and the facts that are yours.

Its own noun and not a flag on `context`, which is what it was. `--mine` meant two different
things on the same command — "file this under me" on a write and "show my page" on a read — and a
flag that changes what a verb IS is a flag somebody will get backwards. Worse, it made the person
dimension look optional: an objective is ALWAYS somebody's, and there is no such thing as the
project's, because the project's north is a milestone now.

`--owner` went with it. A fact is filed under whoever ran the command, resolved through `whoami`
the same way a claim is, so nobody can state somebody else's objective by typing their name.
"""

from __future__ import annotations

import argparse

from ....render.context import render_context
from ....usecases._contextviews import show
from ....usecases._routing import whoami
from ....usecases.context import retire, state
from ._shared import add_actor, add_target, repo_of
from .context import fact_line, scoped

__all__ = ["register", "run"]

MINE = ("objective", "decision", "note")
"""No `rule`: a rule is the project's by definition — "every card, no exceptions" is not something
one person holds. `taskops context rule` is where one is stated, and it is a person-only verb."""


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("me", help="your own objective and the facts filed under you")
    add_target(parser)
    add_actor(parser)
    parser.add_argument("verb", nargs="?", default="show",
                        choices=("show", *MINE, "retire"))
    parser.add_argument("text", nargs="?", default="", help="the fact, or the id to retire")
    parser.add_argument("--labels", default="", help="comma-separated scope")
    parser.add_argument("--files", default="", help="comma-separated edit surface")
    parser.add_argument("--horizon", default="", help="when your objective expires")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    where, who = repo_of(args), str(args.actor)
    if args.verb == "retire":
        return f"retired {retire(where, str(args.text), actor=who)['id']}"
    if args.verb in MINE:
        labels, files = scoped(args)
        stated = state(where, str(args.verb), str(args.text), labels=labels, files=files,
                       horizon=str(args.horizon), owner=whoami(where, who), actor=who)
        return f"stated {fact_line(stated)}"
    return render_context(show(where, actor=who, mine=True))
