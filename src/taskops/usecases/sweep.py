"""`taskops report sweep` — the daily report as a BARRIER rather than as a clock.

A scheduled job that narrates "yesterday" at 00:05 is wrong every time the machine was asleep,
and wrong twice when somebody runs it by hand. State the rule instead — *every day that has
ENDED, has events, and has no narration, gets narrated* — and the trigger stops mattering:
00:05, 9am on wake, and a person typing it converge on the same file, and running it ten times
costs nothing after the first. Claude Code's own scheduling docs ask for exactly this guardrail
("a task scheduled for 9am might run at 11pm if your computer was asleep"); this is it.

Idempotence is therefore the FEATURE, not a nicety. The second run must not merely leave the
files alone — it must not CALL the model, because the model is what a run costs. That is why
selection happens before any narration and why an existing narration is never overwritten: it
may be somebody's edited prose, and it is the one section a machine cannot recover.

Nothing here narrates or pushes by hand. `digest` already writes the dossier, streams the
prose and refuses a file that carries one; `push` already knows the wire. A second copy of
either would be the copy that drifts.
"""

from __future__ import annotations

from pathlib import Path

from .._clock import now
from .._errors import (
    AlreadyNarrating,
    AlreadyWritten,
    BadRequest,
    NarrationFailed,
    NotInitialized,
    TaskopsError,
)
from ..contracts.sweep import Skipped, SweepResult
from ..engine import date_of
from ._range import Selector, parse_date
from ._sweepdays import pending_days
from .dossier import digest
from .pushpull import push as push_remote

__all__ = ["sweep", "LIMIT"]

LIMIT = 7
"""How many days one run will narrate. A repository with two years of history must not turn a
9am wake-up into a hundred model calls, and a week is what a machine that was away for a
holiday actually owes. The rest are counted into `truncated` and taken by the next run."""


def sweep(start: Path | str, *, date: str = "", model: str = "", limit: int = LIMIT,
          push: bool = False, force: bool = False) -> SweepResult:
    """Narrate every ended day that still owes prose. Safe to run on any schedule, twice.

    `force` is the only way to redo a day, and it demands an explicit `date`: "redo whatever
    you think is stale" over a fortnight of edited narrations is not a command anybody means,
    and it is unrecoverable once it has run.

    `limit` of zero or less means no cap — the deliberate "fill the whole hole" of a first run
    on an old repository, which is a decision somebody makes once and never by accident.

    Every refusal is CAUGHT and reported, never raised. A sweep is unattended by definition —
    a lock held by a concurrent run, a report somebody narrated a second ago, one day the
    model would not answer for — and a run that aborts on the first of those leaves the other
    six days unwritten for a reason nobody will read in a cron log.
    """
    days = _targets(start, date, force=force)
    truncated = max(0, len(days) - limit) if limit > 0 else 0
    done = SweepResult(narrated=[], skipped=[], pushed=0, truncated=truncated)
    for day in days[:limit] if limit > 0 else days:
        _narrate(start, day, done, model=model, force=force)
    if push and done["narrated"]:
        _push(start, done)
    return done


def _targets(start: Path | str, date: str, *, force: bool) -> list[str]:
    if not force:
        return pending_days(start, date_of(now()))
    if not date:
        raise BadRequest("--force redoes ONE day and needs --date — it replaces a narration "
                         "that may have been written or edited by hand")
    return [parse_date(date)]


def _narrate(start: Path | str, day: str, done: SweepResult, *,
             model: str, force: bool) -> None:
    """One day, with every way it can decline turned into a sentence.

    `AlreadyNarrating` is the concurrent case and the reason this is not an error: two sweeps
    racing is what a cron entry plus an impatient human looks like, and the right outcome is
    that one of them narrates the day and the other says so.
    """
    try:
        digest(start, Selector(date=day), model=model, force=force)
        done["narrated"].append(day)
    except AlreadyNarrating:
        done["skipped"].append(Skipped(label=day, why="another run is narrating it right now"))
    except AlreadyWritten:
        done["skipped"].append(Skipped(label=day, why="it already carries a narration"))
    except NarrationFailed as failed:
        done["skipped"].append(Skipped(label=day, why=f"the narration failed: {failed}"))


def _push(start: Path | str, done: SweepResult) -> None:
    """ONE round trip at the end, not one per day: a push is a network conversation, and
    seven of them for seven files is seven chances to fail halfway through a backfill."""
    try:
        done["pushed"] = len(push_remote(start).reports.uploaded)
    except NotInitialized:
        done["skipped"].append(Skipped(label="push", why="this project has no remote — run "
                                                         "`taskops remote add` or drop --push"))
    except TaskopsError as failed:
        done["skipped"].append(Skipped(label="push", why=f"the push failed: {failed}"))
