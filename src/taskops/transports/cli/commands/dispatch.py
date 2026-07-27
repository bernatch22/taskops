"""`taskops dispatch` — launch worker agents, one per card."""

from __future__ import annotations

import argparse

from ....render import render_dispatch
from ....usecases import dispatch as launch_workers
from ._shared import add_target, repo_of

__all__ = ["register"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("dispatch", help="launch worker agents for ready cards")
    add_target(parser)
    parser.add_argument("tasks", nargs="*", help="task ids (default: the best ready ones)")
    parser.add_argument("--count", type=int, default=0, help="how many to launch (default 3)")
    parser.add_argument("--prefix", default="", help="worker name prefix (default 'w')")
    parser.add_argument("--model", default="", help="model for the workers")
    parser.add_argument("--actor", default="", help="who is dispatching")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    return render_dispatch(launch_workers(
        repo_of(args), tasks=tuple(str(t) for t in args.tasks), count=int(args.count),
        actor=str(args.actor), prefix=str(args.prefix), model=str(args.model)))
