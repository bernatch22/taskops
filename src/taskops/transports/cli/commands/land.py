"""`taskops land` — merge a finished card's branch into the trunk.

Closing already tries this; the verb exists for the retry, which is the case that matters: a
conflict was resolved by hand or by a worker, and somebody has to say "now".
"""

from __future__ import annotations

import argparse

from ....usecases.landtask import land_task
from ._shared import add_target, repo_of

__all__ = ["register", "run"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("land", help="merge a done card's branch into the trunk")
    parser.add_argument("task", help="the card id")
    parser.add_argument("--no-push", action="store_true",
                        help="merge into the trunk and stop, without publishing. The card stays "
                             "unlanded until a plain `land` pushes it — run your tests in between")
    add_target(parser)
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    card, done = land_task(repo_of(args), str(args.task), push=not args.no_push)
    if done.ok:
        return f"{card} is on {done.trunk} ({done.sha})"
    return f"{card} did not land — {done.why}"
