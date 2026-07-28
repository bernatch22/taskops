"""Read one task in full, or search when you have no id.

No parser of its own any more: `taskops ask` was a command for agents, and agents have
`taskops_ask` over MCP with a better contract. The function stayed exactly where it was,
because `taskops tasks show` and `taskops tasks search` reach THIS — two implementations of
"read a task" is how the CLI and the MCP start disagreeing about what a task looks like.
"""

from __future__ import annotations

import argparse

from ....render import render_search, render_view
from ....usecases import ask as read
from ....usecases import search
from ._shared import repo_of

__all__ = ["run"]


def run(args: argparse.Namespace) -> str:
    """A bare argument, because a human types `taskops ask tk-4f2a` far more often than a
    query — and an id is recognisable on sight, so guessing which one it is costs nothing."""
    what = str(args.what)
    if what.startswith("tk-"):
        return render_view(read(repo_of(args), what, actor=args.actor))
    return render_search(search(repo_of(args), what), what)
