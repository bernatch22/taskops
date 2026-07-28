"""Which days the caller asked for — argparse's flags turned into ONE `Selector`.

Its own module because the refusals are the interesting part and `report.py` already owns the
flag table and the three ways of emitting a dossier. Nothing here reads a repository: it maps
what was typed onto what `usecases` resolves, and says no to combinations that would otherwise
be settled by the order of a chain of ifs.
"""

from __future__ import annotations

import argparse

from ...._errors import BadRequest
from ....usecases import Selector

__all__ = ["selector"]


def selector(args: argparse.Namespace) -> Selector:
    """The window, refusing a MIX of ways of asking for it.

    `report day --last 7d` is somebody who means one of the two and would not notice which
    one won — so neither does taskops. The flags are named after the kind that owns them, and
    borrowing another kind's flag is an error rather than a silently ignored preference.
    """
    if args.kind != "range" and (args.last or args.from_date or args.to):
        raise BadRequest(f"--last, --from and --to belong to `report range` — "
                         f"`report {args.kind}` takes {_instead(str(args.kind))}")
    if args.kind == "all":
        return Selector(whole=True)
    if args.kind != "range":
        return Selector(date=str(args.date))
    if not (args.last or args.from_date):
        raise BadRequest("`report range` needs a window — --last 7d (also 2w, 1m), or "
                         "--from YYYY-MM-DD [--to YYYY-MM-DD]")
    if args.last and args.from_date:
        raise BadRequest("--last and --from are two ways of naming the same start — pick "
                         "one, or the report covers a window nobody asked for")
    return Selector(date=str(args.from_date), to=str(args.to), last=str(args.last))


def _instead(kind: str) -> str:
    """What the kind the caller named DOES accept. Naming the alternative is the difference
    between an error somebody fixes and one they retry with the same flag."""
    return "no window at all — it covers everything" if kind == "all" else "--date"
