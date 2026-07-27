"""`taskops ask` — read one task in full, or search when you have no id."""

from __future__ import annotations

import argparse

from ....render import render_search, render_view
from ....usecases import ask as read
from ....usecases import search
from ._shared import add_target, repo_of

__all__ = ["register"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("ask", help="read a task, or search titles and specs")
    add_target(parser)
    parser.add_argument("what", help="a task id, or free text to search for")
    parser.add_argument("--actor", default="", help="who is calling")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    """A bare argument, because a human types `taskops ask tk-4f2a` far more often than a
    query — and an id is recognisable on sight, so guessing which one it is costs nothing."""
    what = str(args.what)
    if what.startswith("tk-"):
        return render_view(read(repo_of(args), what, actor=args.actor))
    return render_search(search(repo_of(args), what), what)
