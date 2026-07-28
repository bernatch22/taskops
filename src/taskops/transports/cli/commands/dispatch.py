"""Preparing worker agents, one per card — the flags and the call `taskops run` is built on.

`taskops dispatch` was hidden once `taskops run` took over the half of this that starts
processes, and it is gone now: an orchestrator dispatches over MCP (`taskops_dispatch`), and
the person who wants processes types `run`. What stays is this module, because `run`'s flags
are declared here — a second copy of that parser would drift the first time either grew an
option.
"""

from __future__ import annotations

import argparse

from ....render import render_dispatch
from ....usecases import dispatch as launch_workers
from ._shared import add_target, repo_of

__all__ = ["add_dispatch_args", "dispatch_with"]


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


def dispatch_with(args: argparse.Namespace, *, spawn: bool) -> str:
    """The one call both commands make. `spawn` is the only thing either of them decides.

    `--use-api-key` is read with `getattr` because only `run` declares it; `dispatch` keeps the
    flag set it always had rather than growing one that its own help would have to explain."""
    return render_dispatch(launch_workers(
        repo_of(args), tasks=tuple(str(t) for t in args.tasks), count=int(args.count),
        actor=str(args.actor), prefix=str(args.prefix), model=str(args.model),
        dry_run=bool(args.dry_run), spawn=spawn,
        use_api_key=bool(getattr(args, "use_api_key", False))))
