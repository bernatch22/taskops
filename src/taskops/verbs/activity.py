"""activity — the whole story of N cards in ONE read.

`card` answers "what is this card" for one card, and answering it for a whole
chapter meant N calls, N dossiers and a context window spent on the same
milestone header twenty-two times. This is that read done once: the chapter's
header, then one story per card — what it is, where it stands, what was
committed, what was said last, and where it landed.

Four decisions, each a rule of this chapter rather than a preference:

**No diffs, ever.** A story carries `branch`, the commit SHAs with their
numstat, and `merged_into` — POINTERS: an agent that wants the patch runs git
in its own worktree, where the bytes already are. Patch text in a payload is
prose in `events.jsonl` all over again (`core/reports.py`).

**Depth is a LIST cap, never a truncation.** `headline` (the default) carries
the measures and the pointers — state, standing, commits, `merged_into`, the
released note, the seconds — and `thread_total` without the thread. `full` adds
the PROSE: the spec, the criteria, the edit surface, the thread whole. Nothing
is ever cut mid-sentence; a capped list with its honest total is this project's
one answer to "too much" (`pulse.DONE_SHOWN`, `_facts.REPORTS_SHOWN`), because
a reader can act on "0 of 13, depth=full for them" and not on a paragraph that
stops. Where the line falls was MEASURED against this board's two largest
chapters (22 and 16 cards, 2026-08-10) — 76 cards must fit in ~100 KB:

    per card, JSON        headline      full
    the whole story     1.2–1.3 KB   13–14 KB    → 76 cards: 88–95 KB
    of which: commits      0.46 KB
              one event    0.38 KB    (the thread's LAST event ALONE)
              files        0.14 KB

One thread event per card is 29 KB across 76, and the budget does not have it:
a comment here is prose, and prose is unbounded. `tests/test_verbs.py` pins the
76-card budget so a later field cannot quietly spend it.

**`since=` is the cache's cursor, not a second one.** The argument is a `seq`
from a previous answer (every payload carries `seq`), and what moved is read off
`cache.since()` — the keyset `verbs/events.py` pages the log with, for the same
reason: `ts` ties inside a single plan and an offset shifts under a reader.
Cards with no event past the cursor drop out of the list while `cards_total`
still counts them, so "nothing moved" reads as an empty list, never as an empty
chapter.

**A read, for everyone** (`WATCHERS`): it renews the caller's lease exactly as
every other read does — which is nothing at all for `anon`, decided once in
`store/live.py::renew` — and writes nowhere.

The shape of ONE card inside the answer, and the two caps on it, are
`_stories.py` — the same split `pulse.py` and `_rows.py` already have.
"""

from __future__ import annotations

from typing import Any

from . import _args, _facts, _context, _stories
from .. import _clock
from .events import MAX_CURSOR
from .._errors import NotFound, BadRequest
from ._stories import DEPTHS, HEADLINE
from ..core.types import Card, Milestone
from ..store.stores import Stores

DOORS = (
    "activity reads a CHAPTER or a named set of cards: "
    "milestone=ms-… (or nothing, when the board has a single open chapter) "
    "or tasks=[tk-…, tk-…]"
)


def run(stores: Stores, actor: str, args: _args.Args) -> dict[str, Any]:
    now = _clock.now()
    stores.live.renew(actor, now)
    depth = _depth(args)
    since = _args.number(args, "since", default=0, low=0, high=MAX_CURSOR)
    stone, scope = _scope(stores, args)
    cards = stores.state()["cards"]
    live = _facts.holders(stores, now)
    checking, stood = _facts.reviewing(stores, now), _facts.standings(stores)
    filed, reports_total = _facts.reports(stores, stone["id"] if stone else "")
    moved = _moved(stores, since)
    stories = [
        _stories.story(stores, card, now, depth, (cards, live, checking, stood))
        for card in scope
        if moved is None or card["id"] in moved
    ]
    return {
        # The chapter whole — goal, rules, criteria, status: the header every
        # story is read against, sent ONCE instead of once per `card` call.
        "milestone": stone,
        "reports": filed,
        "reports_total": reports_total,
        "depth": depth,
        "since": since,
        # The cursor to send back next time — from `head()`, not from the last
        # story: a chapter where nothing moved must still advance past what
        # happened elsewhere on the board.
        "seq": stores.head(),
        "cards": stories,
        # What the scope HAS, against what this answer carries: with `since=`
        # they differ, and that IS the argument — `done_total` over a filter.
        "cards_total": len(scope),
        "pulse": _context.pulse(stores, actor, now, stone["id"] if stone else ""),
    }


def _depth(args: _args.Args) -> str:
    depth = _args.text(args, "depth", default=HEADLINE) or HEADLINE
    if depth not in DEPTHS:
        raise BadRequest(f"depth={depth!r} is not {' or '.join(DEPTHS)}")
    return depth


def _scope(stores: Stores, args: _args.Args) -> tuple[Milestone | None, list[Card]]:
    """Which cards this call is about: the ones NAMED, else a whole chapter.

    `tasks=` wins over `milestone=` — it is the narrower question, and the cards
    may legitimately span chapters (a wave across two). The header is then the
    chapter they SHARE, or nothing, never one of them picked silently.
    """
    named = _args.strings(args, "tasks")
    if named:
        cards = [_facts.find(stores, task) for task in named]
        shared = {card["milestone"] for card in cards}
        stone = stores.state()["milestones"].get(shared.pop()) if len(shared) == 1 else None
        return stone, cards
    given = _args.text(args, "milestone", default="")
    stone = _facts.in_scope(stores, given)
    if stone is None and given:
        raise NotFound(f"milestone {given} does not exist — taskops_board lists them")
    if stone is None:
        raise BadRequest(DOORS)
    mine = [c for c in stores.state()["cards"].values() if c["milestone"] == stone["id"]]
    # The order `board` puts them in, so the two reads cannot disagree about
    # what comes first: what was planned as urgent, then what was planned first.
    return stone, sorted(mine, key=lambda c: (c["priority"], c["created"]))


def _moved(stores: Stores, since: int) -> set[str] | None:
    """Which cards have an event past `since`, or None when there is no cursor —
    None rather than "every card", because an empty answer has to be able to
    say which of the two it is."""
    if not since:
        return None
    return {event["task"] for _, event in stores.cache.since(since)}
