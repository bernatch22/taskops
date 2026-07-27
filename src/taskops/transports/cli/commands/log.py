"""`taskops log <task>` — read what the agent said while working on a card."""

from __future__ import annotations

import argparse

from ....render import render_log
from ....usecases import session_log
from ._shared import add_target, repo_of

__all__ = ["register"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("log", help="the agent's conversation for a card")
    add_target(parser)
    parser.add_argument("task", help="the task id")
    parser.add_argument("--limit", type=int, default=0,
                        help="entries to keep, newest last (default 400)")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    from ....usecases.log import MAX_ENTRIES

    return render_log(session_log(repo_of(args), str(args.task),
                                  limit=int(args.limit) or MAX_ENTRIES))
