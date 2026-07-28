"""`taskops report` — the generated views."""

from __future__ import annotations

import argparse
from pathlib import Path

from ...._errors import BadRequest
from ....render import render_board, render_day, render_fleet, render_standup
from ....usecases import board, day, digest, fleet, standup, write_report
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
    parser.add_argument("--write", action="store_true",
                        help="day: persist the dossier to .taskops/reports/<date>.md")
    parser.add_argument("--force", action="store_true",
                        help="with --write: regenerate a report that already exists")
    parser.add_argument("--digest", action="store_true",
                        help="day: write it, then have Claude narrate what it means "
                             "(uses your logged-in subscription, never an API key)")
    parser.add_argument("--model", default="",
                        help="with --digest: the model to narrate with")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    where = repo_of(args)
    if args.kind != "day" and (args.write or args.force or args.digest):
        raise BadRequest("--write, --force and --digest only apply to `report day` — every "
                         "other report is regenerated on demand")
    if args.kind == "standup":
        return render_standup(standup(where, since=str(args.since), actor=str(args.actor)))
    if args.kind == "day":
        return _day(args, where)
    if args.kind == "fleet":
        return render_fleet(fleet(where))
    return render_board(board(where))


def _day(args: argparse.Namespace, where: Path) -> str:
    """Printed, or written and its PATH printed.

    The path rather than the dossier: what the caller does next is read or commit that file,
    and a command that dumps 300 lines it just saved makes the one useful line scroll away.
    """
    if args.digest:
        path = digest(where, str(args.date), model=str(args.model),
                      force=bool(args.force))
        return f"narrated {path}"
    if not args.write:
        return render_day(day(where, str(args.date)))
    path = write_report(where, str(args.date), force=bool(args.force))
    return f"wrote {path}"
