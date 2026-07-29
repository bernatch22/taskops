"""`taskops status` — where the project stands, in one screen.

The command somebody types before they start working, so it is built around costing
nothing: one SQLite file, no git subprocess and no socket. `--fetch` is the single
exception and it has to be asked for by name — a status that quietly did a round trip
would be slow exactly when the network is bad, which is when people run it twice.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import IO

from ....render.status import render_status
from ....usecases.status import IDLE_DAYS, status
from ._shared import add_target

__all__ = ["register", "run"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("status", help="where the project stands, in one screen")
    add_target(parser)
    parser.add_argument("--actor", default="",
                        help="whose claims count as `yours` (default: the resolved caller)")
    parser.add_argument("--fetch", action="store_true",
                        help="pull from the remote first — the only thing here that "
                             "touches the network")
    parser.add_argument("--idle-days", type=int, default=IDLE_DAYS,
                        help=f"how long an open card may sit untouched (default: {IDLE_DAYS})")
    parser.add_argument("--no-color", action="store_true", help="never emit escape codes")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    return render_status(
        status(str(args.repo), actor=str(args.actor), fetch=bool(args.fetch),
               idle_days=int(args.idle_days)),
        colour=not args.no_color and _colour(sys.stdout))


def _colour(to: IO[str]) -> bool:
    """Decided HERE, never in the renderer, which is pure and takes it as a parameter.

    A status piped into a file with escape codes in it is a bug, so a non-tty gets plain
    text; `NO_COLOR` is honoured because somebody who exported it meant every tool, not
    the ones that remembered to check.
    """
    return bool(getattr(to, "isatty", bool)()) and not os.environ.get("NO_COLOR")
