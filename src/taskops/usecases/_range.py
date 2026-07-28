"""Which days a report covers — the selector a human types, resolved to two dates.

Four ways of saying the same thing (one day, the last N, an explicit span, everything) and
ONE place that turns any of them into `from_date, to_date`. That is deliberate: the dossier
writer needs the same answer as the reader, and a second resolution is how a file named
`2026-07-22..2026-07-28.md` ends up holding a different week.

Strict, like `parse_window` and `parse_date`. A selector nobody can read is REFUSED and never
widened to something plausible: a report quietly covering the wrong month looks exactly like
a correct one, and it is the shape somebody pastes into a review.
"""

from __future__ import annotations

from typing import NamedTuple

from .._clock import now
from .._errors import BadRequest
from ..engine import date_of, first_date, shift
from ..storage import Store

__all__ = ["is_day", "Selector", "resolve", "parse_date"]

_UNITS = {"d": 1, "w": 7}


class Selector(NamedTuple):
    """What the caller asked for, before a store is open. Defaults to today."""

    date: str = ""
    """The START of the window, or the whole of it when nothing else is set: `today`,
    `yesterday`, or `YYYY-MM-DD` — whatever `parse_date` accepts."""

    to: str = ""
    """The last day, INCLUSIVE. Empty means today for a range, and `date` for a single day."""

    last: str = ""
    """`7d`, `2w`, `1m` — a span ending at `to`."""

    whole: bool = False
    """`report all`: from the log's first event to today."""


def resolve(store: Store, sel: Selector) -> tuple[str, str, str]:
    """`Selector` -> the two dates a `period_report` runs between, and what to call them.

    Order matters: `whole` wins, then `last`, then an explicit pair, then the single day.
    They are not combinable, and letting one silently override another inside a report would
    be worse than the argument parser refusing the combination up front.

    `all` is labelled `all` and not by its dates on purpose: it is a standing name for "the
    whole project", so `report all --digest` keeps updating ONE file instead of leaving a
    trail of near-identical ones whose end date happens to differ.
    """
    if sel.whole:
        return first_date(store), parse_date(sel.to), "all"
    if sel.last:
        end = parse_date(sel.to)
        return _back(end, sel.last), end, ""
    if sel.to:
        return parse_date(sel.date), parse_date(sel.to), ""
    return parse_date(sel.date), parse_date(sel.date), ""


def _back(end: str, last: str) -> str:
    """`2026-07-28`, `7d` -> `2026-07-22`. INCLUSIVE of both ends: `7d` is seven days of
    work, not seven days ago plus today, which would be eight."""
    raw = last.strip().lower()
    number, unit = raw[:-1], raw[-1:]
    if not number.isdigit() or int(number) <= 0 or unit not in (*_UNITS, "m"):
        raise BadRequest(f"`{last}` is not a span — use a positive number then d, w or m, "
                         f"e.g. 7d, 2w or 1m")
    if unit == "m":
        return shift(shift(end, months=-int(number)), days=1)
    return shift(end, days=1 - int(number) * _UNITS[unit])


def parse_date(text: str) -> str:
    """`yesterday` -> `2026-07-27`. Strict, for the same reason `parse_window` is.

    `yesterday` is 24 hours back read as a LOCAL date rather than "today minus one" in
    arithmetic on a date, which would have to know how long a month is. The calendar is
    libc's problem, and libc is the only one that knows about the two days a year that are
    not 24 hours long.
    """
    raw = text.strip().lower()
    if raw in ("", "today"):
        return date_of(now())
    if raw == "yesterday":
        return date_of(now() - 86400.0)
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-" and raw.replace("-", "").isdigit():
        return raw
    raise BadRequest(f"`{text}` is not a day — use `today`, `yesterday`, or a date "
                     f"like 2026-07-28")


def is_day(label: str) -> bool:
    """Whether a report label names one calendar day. The ONE place this shape is read:
    the index and the report reader both branch on it, and two copies is how one of them
    keeps accepting a shape the other started refusing."""
    return (len(label) == 10 and label[4] == "-" and label[7] == "-"
            and label.replace("-", "").isdigit())
