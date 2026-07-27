"""`taskops recover` — hand back the cards of workers that died."""

from __future__ import annotations

import argparse

from ....render import render_recover
from ....usecases import recover as run_recovery
from ._shared import add_target, repo_of

__all__ = ["register"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("recover", help="release cards held by workers that went silent")
    add_target(parser)
    parser.add_argument("--force", action="store_true",
                        help="release even the workers still reporting")
    parser.add_argument("--grace", type=float, default=0.0,
                        help="seconds of silence to tolerate (default: the fleet's own grace)")
    parser.add_argument("--actor", default="", help="who is recovering")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    from ...._clock import HEARTBEAT_GRACE

    return render_recover(run_recovery(
        repo_of(args), actor=str(args.actor), force=bool(args.force),
        grace=float(args.grace) or HEARTBEAT_GRACE))
