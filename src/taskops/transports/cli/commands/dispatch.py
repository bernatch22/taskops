"""`taskops dispatch` — prepare worker agents, one per card.

Hidden since `taskops run` took over the half of this that starts processes. The flags are
declared here and `run` imports them, so the two commands cannot drift into taking
different options — which is what a second copy of this parser would produce the first time
one of them grew a flag.
"""

from __future__ import annotations

import argparse

from ....render import render_dispatch
from ....usecases import dispatch as launch_workers
from ._shared import add_target, repo_of

__all__ = ["register", "add_dispatch_args", "dispatch_with"]


def add_dispatch_args(parser: argparse.ArgumentParser) -> None:
    """Every flag a dispatch takes except `--spawn` — which is the one thing that tells the
    two commands apart, and so is declared by each of them."""
    add_target(parser)
    parser.add_argument("tasks", nargs="*", help="task ids (default: the best ready ones)")
    parser.add_argument("--count", type=int, default=0, help="how many to launch (default 3)")
    parser.add_argument("--prefix", default="", help="worker name prefix (default 'w')")
    parser.add_argument("--model", default="", help="model for the workers")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run",
                        help="show what would launch, change nothing")
    parser.add_argument("--actor", default="", help="who is dispatching")


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("dispatch", help="launch worker agents for ready cards")
    add_dispatch_args(parser)
    parser.add_argument("--spawn", action="store_true",
                        help="deprecated: use taskops run")
    parser.set_defaults(run=run)


def dispatch_with(args: argparse.Namespace, *, spawn: bool) -> str:
    """The one call both commands make. `spawn` is the only thing either of them decides."""
    return render_dispatch(launch_workers(
        repo_of(args), tasks=tuple(str(t) for t in args.tasks), count=int(args.count),
        actor=str(args.actor), prefix=str(args.prefix), model=str(args.model),
        dry_run=bool(args.dry_run), spawn=spawn))


def run(args: argparse.Namespace) -> str:
    return dispatch_with(args, spawn=bool(args.spawn))
