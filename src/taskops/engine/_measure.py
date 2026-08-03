"""What counts as work, what a gap is worth, and who a gap belongs to.

The MEASURE, split from the folds that read it because the module budget said the two were one thing
too many — and it was right: below is arithmetic that has to be argued once, above it are three
readers that must not each argue it again.

Nothing records when somebody stopped working. What the log has is WHEN each thing happened, so the
only defensible answer is built out of the gaps between one actor's consecutive events — each gap
capped, and each attributed to exactly ONE card: the card of the event that CLOSES it, because the
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
"""The most a single gap may contribute, in seconds.

Thirty minutes because of how the events actually arrive: an agent's calls on one card land seconds
to a few minutes apart, so a gap past half an hour is somebody having left rather than somebody
thinking. It is deliberately ONE number and not a per-kind table — a rule a reader can hold is worth
more here than a fit, since the output is a bound and not an estimate.
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
        seconds[task] = seconds.get(task, 0.0) + min(later - earlier, GAP)
    for _, task in ordered:
        counts[task] = counts.get(task, 0) + 1
    return seconds, counts
