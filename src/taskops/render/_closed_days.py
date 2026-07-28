"""The `## Cerrado` section — flat for one day, grouped BY DAY for anything wider.

Split from `day` because the grouping is the only thing a month-long report changes, and the
module that decides the ORDER of a dossier should not grow a second concern the day somebody
asks for a quarter.

A hundred cards under one heading is a wall nobody scrolls. Under a heading per day, newest
first, the same hundred cards answer "what happened the week of the 22nd" by eye — which is
the question a range report exists for.
"""

from __future__ import annotations

import time

from ..contracts import ClosedCard, Event, PeriodReport
from ._dossier import card_block

__all__ = ["closed_section"]


def closed_section(day: PeriodReport) -> list[str]:
    """The heading, the cards, and — when the cap cut some — how many are missing."""
    one_day = day["from_date"] == day["to_date"]
    if not day["closed"]:
        nothing = "Nothing closed on this day." if one_day else "Nothing closed in this window."
        return ["## Cerrado", "", nothing, *_dropped(day), ""]
    count = len(day["closed"])
    body = (_flat(day["closed"], day["conversations"]) if one_day
            else _by_day(day["closed"], day["conversations"]))
    return [f"## Cerrado ({count})", "", body, *_dropped(day), ""]


def _dropped(day: PeriodReport) -> list[str]:
    """Never a silent truncation. The same rule the activity view follows: a report that shows
    200 of 400 cards without saying so is worse than one that shows none, because the reader
    has no way to know the number they are about to quote is short."""
    if not day["dropped"]:
        return []
    return ["", f"_{day['dropped']} more card(s) closed in this window and are not shown — "
                f"narrow the range to read them._"]


def _flat(cards: list[ClosedCard], said: list[Event]) -> str:
    """One day: no day headings. A `## 2026-07-28` under a `# 2026-07-28` title is noise, and
    it is what keeps a single day's report byte-identical to what it always was."""
    return "\n\n".join("\n".join(card_block(card, said)) for card in cards)


def _by_day(cards: list[ClosedCard], said: list[Event]) -> str:
    """Newest day first, with its own count. The cards inside a day keep the log's order —
    oldest close first — so a day still reads the way the day happened."""
    days: dict[str, list[ClosedCard]] = {}
    for card in cards:
        days.setdefault(_date_of(card["done_ts"]), []).append(card)
    return "\n\n".join(f"### {date} ({len(group)})\n\n" + _flat(group, said)
                       for date, group in sorted(days.items(), reverse=True))


def _date_of(ts: float) -> str:
    """The LOCAL date a close landed on — the same calendar the window was cut on, so a card
    closed at 23:50 heads the day its reader worked, not the next one in UTC."""
    return time.strftime("%Y-%m-%d", time.localtime(ts))
