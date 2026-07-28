"""`report sweep` in a terminal — the backfill's outcome, INCLUDING the ways it did nothing.

Its own module for the same reason `_digest` is: `report` is already at its budget, and this
command's whole job is a report about a report. The empty run is the COMMON one — that is what
a barrier is for — so "nothing to narrate" has to be a sentence a cron log can be read for. An
exit code alone cannot tell a guardrail that is working from one that has been failing since
Tuesday, and the second is indistinguishable from the first until somebody wants the week.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ....contracts.sweep import SweepResult
from ....usecases.sweep import sweep

__all__ = ["run_sweep"]


def run_sweep(where: Path, args: argparse.Namespace) -> str:
    """`--date` is forwarded only under `--force`, which is the one mode that takes a day.

    Without `--force` the window is the LOG's and not the caller's — a sweep that honoured a
    date would be `report day` with extra steps. And `--date` defaults to empty rather than to
    `today` precisely so that `--force` alone is refused instead of quietly redoing today.
    """
    return _lines(sweep(where, date=str(args.date) if args.force else "",
                        model=str(args.model), limit=int(args.limit),
                        push=bool(args.push), force=bool(args.force)))


def _lines(done: SweepResult) -> str:
    head = (": " + ", ".join(done["narrated"]) if done["narrated"]
            else " — every ended day is already written up")
    out = [f"narrated {len(done['narrated'])} day(s){head}"]
    out += [f"  skipped {row['label']} — {row['why']}" for row in done["skipped"]]
    out += [f"  {done['truncated']} more day(s) left by --limit; run it again"] \
        * bool(done["truncated"])
    out += [f"  pushed {done['pushed']} report(s)"] * bool(done["pushed"])
    return "\n".join(out)
