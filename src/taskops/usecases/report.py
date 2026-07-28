"""`taskops_report` — the projections, and the window parsing that feeds them.

The reports are generated from the log and never written by hand, which is the whole
claim: a standup nobody typed cannot be out of date, and it cannot flatter anybody
either. What this module owns is turning a human's `24h` into a timestamp.
"""

from __future__ import annotations

from pathlib import Path

from .._clock import now
from .._errors import BadRequest
from ..contracts import Activity, Board, DayReport, Fleet, PeriodReport, Standup
from ..engine import activity as build_activity
from ..engine import board as build_board
from ..engine import day_report as build_day
from ..engine import fleet as build_fleet
from ..engine import period_report as build_period
from ..engine import standup as build_standup
from ._project import project
from ._range import Selector, parse_date, resolve

__all__ = ["board", "standup", "fleet", "activity", "day", "period", "parse_window",
           "parse_date", "DEFAULT_WINDOW", "HISTORY_WINDOW"]

DEFAULT_WINDOW = "24h"

HISTORY_WINDOW = "30d"
"""The activity view's default. Wider than a standup's on purpose: one asks what happened since
yesterday, the other is where somebody goes to find out what was ever done here."""

_UNITS = {"m": 60.0, "h": 3600.0, "d": 86400.0, "w": 604800.0}


def board(start: Path | str) -> Board:
    with project(start) as store:
        return build_board(store)


def standup(start: Path | str, *, since: str = DEFAULT_WINDOW, actor: str = "") -> Standup:
    with project(start) as store:
        return build_standup(store, since=now() - parse_window(since), actor=actor)


def activity(start: Path | str, *, since: str = HISTORY_WINDOW) -> Activity:
    with project(start) as store:
        return build_activity(store, since=now() - parse_window(since))


def fleet(start: Path | str) -> Fleet:
    with project(start) as store:
        return build_fleet(store)


def day(start: Path | str, date_text: str = "") -> DayReport:
    with project(start) as store:
        return build_day(store, parse_date(date_text))


def period(start: Path | str, sel: Selector | None = None) -> PeriodReport:
    """The report over whatever window the selector names — a day, a week, or all of it.

    `day` above is this with both ends on the same date; keeping it as its own name is for
    the callers that only ever want one, not a second code path.
    """
    with project(start) as store:
        return build_period(store, *resolve(store, sel or Selector()))




def parse_window(text: str) -> float:
    """`24h` -> 86400.0. Raises on anything it cannot read.

    Strict rather than defaulting, unlike most readers here: a window silently read as
    24 hours when the caller wrote `7days` produces a report that is WRONG and looks
    right, and a standup that quietly covers the wrong period is worse than an error.
    """
    raw = text.strip().lower()
    if not raw:
        return parse_window(DEFAULT_WINDOW)
    number, unit = raw[:-1], raw[-1:]
    if unit not in _UNITS or not number.isdigit() or int(number) <= 0:
        raise BadRequest(f"`{text}` is not a window — use a positive number then "
                         f"one of {', '.join(sorted(_UNITS))}, e.g. 24h or 7d")
    return int(number) * _UNITS[unit]
