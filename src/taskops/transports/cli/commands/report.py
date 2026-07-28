"""`taskops report` — the generated views."""

from __future__ import annotations

import argparse

from ....render import render_board, render_day, render_fleet, render_standup
from ....usecases import board, day, fleet, standup
from ._shared import add_target, repo_of

__all__ = ["register"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("report", help="board, standup, day, or fleet")
    add_target(parser)
    parser.add_argument("kind", nargs="?", default="board",
                        choices=("board", "standup", "day", "fleet"))
    parser.add_argument("--since", default="24h", help="standup window: 24h, 7d, 30m")
    parser.add_argument("--date", default="today",
                        help="which day the dossier covers: today, yesterday, YYYY-MM-DD")
    parser.add_argument("--actor", default="", help="restrict a standup to one actor")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    where = repo_of(args)
    if args.kind == "standup":
        return render_standup(standup(where, since=str(args.since), actor=str(args.actor)))
    if args.kind == "day":
        return render_day(day(where, str(args.date)))
    if args.kind == "fleet":
        return render_fleet(fleet(where))
    return render_board(board(where))
