"""`taskops report` — the generated views."""

from __future__ import annotations

import argparse
from pathlib import Path

from ...._errors import BadRequest
from ....render import render_board, render_day, render_fleet, render_standup
from ....usecases import (
    Selector,
    board,
    fleet,
    period,
    standup,
    write_report,
)
from ._digest import stream_digest
from ._shared import add_target, repo_of
from ._window import selector

__all__ = ["register", "DOSSIERS"]

DOSSIERS = ("day", "range", "all")
"""The kinds that cover a span of days and can therefore be written and narrated. `board` and
`standup` cannot: one is a snapshot with no window, the other moves every time it is run."""


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("report", help="board, standup, day, range, all, or fleet")
    add_target(parser)
    parser.add_argument("kind", nargs="?", default="board",
                        choices=("board", "standup", "day", "range", "all", "fleet"))
    parser.add_argument("--since", default="24h", help="standup window: 24h, 7d, 30m")
    parser.add_argument("--date", default="today",
                        help="which day the dossier covers: today, yesterday, YYYY-MM-DD")
    parser.add_argument("--last", default="",
                        help="range: how far back from --to, e.g. 7d, 2w, 1m")
    parser.add_argument("--from", dest="from_date", default="",
                        help="range: the first day, YYYY-MM-DD")
    parser.add_argument("--to", default="",
                        help="range: the last day (inclusive), YYYY-MM-DD; default today")
    parser.add_argument("--actor", default="", help="restrict a standup to one actor")
    parser.add_argument("--write", action="store_true",
                        help="persist the dossier to .taskops/reports/<label>.md")
    parser.add_argument("--force", action="store_true",
                        help="with --write: regenerate a report that already exists")
    parser.add_argument("--digest", action="store_true",
                        help="write it, then have Claude narrate what it means "
                             "(uses your logged-in subscription, never an API key)")
    parser.add_argument("--model", default="",
                        help="with --digest: the model to narrate with")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    where = repo_of(args)
    if args.kind not in DOSSIERS and (args.write or args.force or args.digest):
        raise BadRequest("--write, --force and --digest only apply to `report day`, "
                         "`report range` and `report all` — a board and a standup are "
                         "regenerated on demand")
    if args.kind == "standup":
        return render_standup(standup(where, since=str(args.since), actor=str(args.actor)))
    if args.kind in DOSSIERS:
        return _dossier(args, where, selector(args))
    if args.kind == "fleet":
        return render_fleet(fleet(where))
    return render_board(board(where))


def _dossier(args: argparse.Namespace, where: Path, sel: Selector) -> str:
    """Printed, or written and its PATH printed.

    The path rather than the dossier: what the caller does next is read or commit that file,
    and a command that dumps 300 lines it just saved makes the one useful line scroll away.
    """
    if args.digest:
        return stream_digest(where, sel, kind=str(args.kind), model=str(args.model),
                             force=bool(args.force))
    if not args.write:
        return render_day(period(where, sel))
    return f"wrote {write_report(where, sel, force=bool(args.force))}"
