"""One card's STORY — the row `activity` sends per card, and the caps on it.

Split out of `activity.py` along the line `_rows.py` was split out of
`pulse.py`: that file owns the CALL (which cards, which cursor, what the
payload is made of), this one owns the shape of a single card inside it, so the
two caps and the depth vocabulary sit together with the measurement that set
them.

A story is the `board` row plus what a row cannot say — where it stands with
its reviewer, what was committed, where it landed, how long it was worked, what
the last worker left. Two lists are capped here and each travels with its
honest total, which is this chapter's rule and the whole codebase's idiom
(`pulse.DONE_SHOWN`, `_facts.REPORTS_SHOWN`).
"""

from __future__ import annotations

from typing import Any

from . import _rows, _facts, _context
from ..core import graph, review
from ..core.types import Card
from ..store.stores import Stores

HEADLINE, FULL = "headline", "full"
DEPTHS = (HEADLINE, FULL)

THREAD_HEADLINE = 0
"""How many of a card's events ride along at `headline`, newest LAST.

Zero — the cap, honestly set, and what the budget pays for
(`activity.py`'s table): one event per card is 0.38 KB, which is 29 KB across
76 cards and a third of the whole allowance, spent on whichever cards are
loudest. Little is lost, because `state`, `standing` (the reviewer's note
verbatim), `resume` (the last worker's) and `merged_into` already say where a
card stopped and why, with `thread_total` for how much talk is behind that.

A number rather than a flag, because it is a CAP and caps get tuned: raise it
the day the budget has room, and the measurement is what says whether it does."""

COMMITS_SHOWN = 10
"""And how many commits, newest LAST — the only other list here that grows
without a bound anybody controls.

Measured on this board (2026-08-10): 1.6 commits per card, the busiest card
five. So this cap does not bite today and is not meant to — it is there because
`commits` is the one field a single pathological card could spend the whole
chapter's budget on, and a cap nobody notices is exactly the right size.
`commits_total` says the real number either way, so a reader is never told
five when there were forty."""


World = tuple[dict[str, Card], dict[str, str], dict[str, str], dict[str, review.Standing]]
"""What every story is read against, gathered ONCE for the call: the card index,
work leases, review leases, standings. Per-card, those four are the N+1 that
made a chapter-wide dossier unaffordable in the first place."""


def story(stores: Stores, card: Card, now: float, depth: str, world: World) -> dict[str, Any]:
    """One card's whole story: the `board` row as the spine — so a card reads the
    same in both payloads — with what a row cannot say folded in beside it."""
    cards, live, checking, stood = world
    events = stores.events(card["id"])
    commits = _facts.commits_of(events)
    standing = stood.get(card["id"])
    row = _rows.row(stores, card, now, live)
    if depth != FULL:
        # The edit surface is what `board` rows are for — planning the next wave
        # against who is in which files. A story is what HAPPENED, and this is
        # 10 KB of the 76-card budget (`activity.py`'s table).
        row.pop("files")
    out = row | {
        "state": graph.derived(cards, card, live, checking, stood),
        "status": card["status"],
        "after": card["after"],
        "parent": card["parent"],
        "review": card.get("review", False),
        # The three pointers into git. This is the whole of "no diffs": a reader
        # that wants the patch has the branch, the shas and where it landed.
        "branch": _facts.branch_of(card),
        "merged_into": _facts.merged_into(events),
        "commits": [event["body"] for event in commits[-COMMITS_SHOWN:]],
        "commits_total": len(commits),
        # Verbatim, exactly as the dossier shows it: a verdict summarised is a
        # verdict a worker rebuilds against instead of fixing against.
        "standing": standing._asdict() if standing and standing.submitted_at else None,
        "resume": _facts.last_release(events),
        "seconds": _context.attended(events),
        "thread": events if depth == FULL else events[len(events) - THREAD_HEADLINE :],
        "thread_total": len(events),
    }
    if depth == FULL:
        out |= {"spec": card["spec"], "criteria": card["criteria"]}
    return out
