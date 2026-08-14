"""What a `window=` spelling MEANS — one vocabulary, one place.

`report` folds events over a span; this module decides what span a caller asked
for and what to call it on screen. They are split because they answer different
questions: the fold is arithmetic over rows, this is calendar parsing, and the
budget for one module is not big enough to hold both honestly.

Four forms, and every one of them resolves through `core/hours.py` so that the
DST rule written there holds for all of them: both edges of a span come out of
the same zoneinfo walk, never an opening stamp plus a count of seconds.

    7d        the last N calendar days, 1..90 — the sliding figure
    month     this calendar month in the caller's tz, first midnight → today
    2026-07   that calendar month, closed on BOTH edges
    total     the whole log, the figure that only grows

An unrecognised spelling is REFUSED and the refusal names all four. The earlier
`days()` fell back to 7 for anything it did not understand, which is how `7dd`
or `august` becomes a plausible number nobody questions.
"""

from __future__ import annotations

from typing import NamedTuple

from ..core import hours
from .._errors import Refused

#: The month names a label is printed with. English, like every other word the
#: board sends; the reader's locale is the reader's business.
MONTHS = "January February March April May June July August September October November December"


class Span(NamedTuple):
    """A window, resolved: what was asked, what it measured, what to call it.

    It rides on the answer whole (`window` in the payload), so a screen titles
    itself "August 2026" instead of inferring a month from two epoch floats.
    """

    window: str
    kind: str
    label: str
    start: float
    end: float


def parse(window: str, now: float, tz: str) -> Span:
    """`7d` · `month` · `YYYY-MM` · `total` → the span it names, read in `tz`.

    An OPEN-ended span — `month` and `total`, the two that run up to the present
    — closes on the next local midnight, exactly as `Nd` already does. Not on
    `now`: every edge here is half-open, so a span ending at `now` excludes the
    event stamped `now`, and the event that CLOSES the current interval is
    usually that one. Ending on `now` silently dropped the last block of work
    from the very window a person opens to see it.
    """
    text = window.strip().lower() or "7d"
    today = hours.day_bounds(now, tz)[1]
    if text == "total":
        return Span(text, "total", "all time", 0.0, today)
    if text == "month":
        start, _ = hours.month_bounds(now, tz)
        return Span(text, "month", label(*hours.month_of(now, tz)), start, today)
    named = _named_month(text, tz)
    if named is not None:
        return named
    span = days(text)
    if span is None:
        raise Refused(
            f"window={window!r} is not a window: use Nd (e.g. 7d), month, "
            "YYYY-MM (e.g. 2026-07) or total"
        )
    spans = hours.windows(now, tz, span)
    return Span(f"{span}d", "days", f"{span} days", spans[0][1], spans[-1][2])


def days(window: str) -> int | None:
    """`7d`, `7`, `1d` → an integer number of calendar days, 1..90 — else None."""
    text = window.strip().lower().removesuffix("d") or "7"
    return max(1, min(90, int(text))) if text.isdigit() else None


def label(year: int, month: int) -> str:
    return f"{MONTHS.split()[month - 1]} {year}"


def _named_month(text: str, tz: str) -> Span | None:
    if len(text) != 7 or text[4] != "-" or not (text[:4].isdigit() and text[5:].isdigit()):
        return None
    year, month = int(text[:4]), int(text[5:])
    if not 1 <= month <= 12:
        return None
    start, end = hours.month_edges(year, month, tz)
    return Span(text, "month", label(year, month), start, end)
