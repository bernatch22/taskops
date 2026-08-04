"""What counts as work, what a gap is worth, and who a gap belongs to.

The MEASURE, split from the folds that read it because the module budget said the two were one thing
too many — and it was right: below is arithmetic that has to be argued once, above it are three
readers that must not each argue it again.

Nothing records when somebody stopped working. What the log has is WHEN each thing happened, so the
only defensible answer is built out of the gaps between one actor's consecutive events — each gap under the
threshold attributed to exactly ONE card: the card of the event that CLOSES it, because the
work inside a gap is the work that produced the next event.

One card per gap is what makes every number here reconcile with every other — see `_attribute`.

The cap is the whole honesty of it. An event and the next one six hours later are not six hours of
work, and a fold that added the raw gap would report a night's sleep as effort on whatever card
happened to be open. Capped, that pair contributes `GAP` and no more, so the total is a LOWER BOUND
on attention rather than a guess at a session. Every surface that draws it has to say so — this
project has already paid for a number that looked complete and was not (`D1`, and the marks that
publish their own coverage).
"""

from __future__ import annotations

from ..contracts import Event

# From the module that defines it rather than the barrel: `contracts/__init__` is at its code
# budget, and one more re-export would push it over for the sake of a shorter import line.


__all__ = ["worked", "attribute", "GAP", "WORK"]

WORK: frozenset[str] = frozenset({
    "claimed", "released", "status", "comment", "commit", "branch", "blocked", "unblocked",
    "handoff", "review", "eval", "done", "message", "activity", "landed", "inferred",
})
"""The kinds that mean somebody was ON a card, and the filter every fold here applies first.

Found by running it. A `plan` of twenty-four cards is ONE call, and a `tasks edit --milestone` over
sixty-two of them is one loop — but every one of those writes an event, in the same second, on a
different card. Unfiltered, the sitting fold read that as *sixty-two cards worked at the same time*,
which is a sentence about a script.

So `created`, `edited`, `acceptance`, `context`, `milestone` and `policy` are out: they record that
the BOARD changed, not that somebody was working. The difference is not cosmetic — a batch write is
exactly the shape that inflates both numbers here, and both numbers exist to be trusted.

`activity` stays in, and it is the strongest evidence there is: it is a session's heartbeat, written
when a tool ran or a file was touched.
"""

GAP = 30 * 60.0
"""The gap that means somebody LEFT, in seconds. Past it, a gap contributes NOTHING.

Thirty minutes because of how the events actually arrive: an agent's calls on one card land seconds
to a few minutes apart, so a gap past half an hour is a departure rather than somebody thinking.

It DROPS rather than caps, and the first version got this wrong: it added `min(gap, GAP)`, billing
thirty minutes of "attention" for every overnight gap — an estimate wearing a floor's name, since
nothing says anybody stayed a single second after that last event. It was caught by arithmetic: the
sitting fold cuts on this same threshold, so every sitting BOUNDARY added an invisible half hour and
the per-card totals ran ahead of the sum of the sitting spans by exactly 30m × boundaries (measured:
−90m, −300m, −510m on one board, all multiples of 30). One threshold must mean one thing: past it,
the sitting ends and the time is zero. That is what makes the two decompositions of the header —
by sitting and by card — add up to the same number, which is how a reader checks any of it.
"""


def worked(events: list[Event]) -> list[Event]:
    """Only the events that mean somebody was on a card. See `WORK` for why, and for what it cost
    to find out. Applied by every fold in this module, so the two numbers cannot disagree."""
    return [event for event in events if event["kind"] in WORK]


def attribute(ordered: list[tuple[float, str]]) -> tuple[dict[str, float], dict[str, int]]:
    """Each capped gap between consecutive stamps, credited to the LATER stamp's card — once.

    The whole arithmetic of this module, in one place on purpose: the profile's rows, a sitting's rows
    and the board's per-card totals must be the same fold, or a card says two things in two places.

    ONCE is the load-bearing word. The first version gave each card the gaps between ITS OWN events,
    and in an interleaved sitting those overlap: `a(0) b(2m) a(4m) b(6m)` is a six-minute sitting
    where `a` claimed 0→4 and `b` claimed 2→6 — eight minutes drawn inside a span of six. A reader
    summed the rows against the header and caught it. Credited to the closing card, the minutes
    PARTITION the span.

    A card touched once can still accrue time (the gap leading INTO its one event); a stream of one
    event accrues none, because there is no gap on either side of it and nothing is invented.
    """
    seconds: dict[str, float] = {}
    counts: dict[str, int] = {}
    for (earlier, _), (later, task) in zip(ordered, ordered[1:], strict=False):
        # DROPPED past the threshold, never capped — see `GAP` for the arithmetic that caught the
        # capped version lying. A gap that ended the sitting contributes nothing to any card.
        if later - earlier <= GAP:
            seconds[task] = seconds.get(task, 0.0) + (later - earlier)
    for _, task in ordered:
        counts[task] = counts.get(task, 0) + 1
    return seconds, counts
