"""How long an actor was ON a card, measured from the log and bounded from below.

Nothing records when somebody stopped working. What the log has is WHEN each thing happened, so the
only defensible answer is built out of the gaps between one actor's consecutive events — each gap
capped, and each attributed to exactly ONE card: the card of the event that CLOSES it, because the
work inside a gap is the work that produced the next event.

One card per gap is what makes every number here reconcile with every other. The first version gave
each card the gaps between its own events, and in an interleaved sitting those gaps OVERLAP:
a(0m) → b(2m) → a(4m) → b(6m) is a six-minute sitting where `a` claimed 0→4 and `b` claimed 2→6 —
eight minutes drawn inside a span of six, and a reader checked the sum against the span and caught
it. Attributed, the per-card minutes of a sitting add up to exactly its span.

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
from ..contracts.spent import Attended, Stretch

__all__ = ["attended", "stretches", "per_card", "worked", "GAP", "WORK"]

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


def attended(events: list[Event]) -> list[Attended]:
    """One actor's events, folded to time per card. Longest first.

    The caller passes ONE actor's events — the split is the caller's, because `history.rolls` has
    already grouped them and grouping twice is how two answers about the same actor start to differ.

    Walks the actor's WHOLE stream in time order, not each card's own events: each capped gap goes
    to the card of the event that closes it, so the minutes of an interleaved sitting add up to its
    span instead of overlapping (see the module docstring for the shape that caught this).

    Sorted by `ts` before subtracting, which is not defensive: a `git pull` merges two ends of a log,
    so events reach a clone out of order, and a fold that trusted arrival order would take a
    difference backwards and count nothing.
    """
    seconds, counts = _attribute(
        sorted(((e["ts"], e["task"]) for e in worked(events)), key=lambda pair: pair[0]))
    out = [Attended(task=task, seconds=seconds.get(task, 0.0), events=n)
           for task, n in counts.items()]
    return sorted(out, key=lambda a: (-a["seconds"], -a["events"], a["task"]))


def _attribute(ordered: list[tuple[float, str]]) -> tuple[dict[str, float], dict[str, int]]:
    """Each capped gap between consecutive stamps, credited to the LATER stamp's card — once.

    The whole arithmetic of this module, in one place on purpose: the profile's per-card rows and
    the board's per-card totals must be the same fold, or a card says two things in two places.
    A card touched once can still accrue time here (the gap leading INTO its one event), and a
    stream of one event accrues none: there is no gap on either side of it and nothing is invented.
    """
    seconds: dict[str, float] = {}
    counts: dict[str, int] = {}
    for (earlier, _), (later, task) in zip(ordered, ordered[1:], strict=False):
        seconds[task] = seconds.get(task, 0.0) + min(later - earlier, GAP)
    for _, task in ordered:
        counts[task] = counts.get(task, 0) + 1
    return seconds, counts


def stretches(events: list[Event]) -> list[Stretch]:
    """One actor's events cut into SITTINGS, newest first. A sitting with several cards in it is
    work that happened at the same time.

    Cut on the same `GAP` the time is capped at, and that is not a coincidence — it is the same
    claim made twice. A gap past the cap is somebody having left, so it ends the sitting; anything
    closer is one continuous stretch of attention, and the distinct cards inside it were being
    alternated between rather than worked one after the other on different days.

    "At the same time" and not "the same day": a day groups by the calendar, which says nothing
    about whether somebody had two things open. This groups by the log's own evidence of continuity.

    Per ACTOR, and the caller must respect that. Two of a dev's agents running in parallel are two
    sittings, not one: merging them would invent simultaneity nobody had, since the whole point of
    an agent is that a developer has several pairs of hands that do NOT share attention.
    """
    ordered = sorted(worked(events), key=lambda e: e["ts"])
    runs: list[list[Event]] = []
    for event in ordered:
        if runs and event["ts"] - runs[-1][-1]["ts"] <= GAP:
            runs[-1].append(event)
        else:
            runs.append([event])
    return [_sitting(run) for run in reversed(runs)]


def _sitting(run: list[Event]) -> Stretch:
    """A run's span and the cards in it, in the order they were first touched — which is the order
    somebody actually opened them, and the only ordering here that carries information."""
    seen: list[str] = []
    for event in run:
        if event["task"] not in seen:
            seen.append(event["task"])
    return Stretch(started=run[0]["ts"], ended=run[-1]["ts"], tasks=seen, events=len(run))


def per_card(rows: list[tuple[str, str, str, float]]) -> dict[str, float]:
    """Every card's attended time, from one flat read of the log. `(task, actor, kind, ts)` in.

    Grouped by ACTOR and attributed along each actor's own stream — never grouped by card, which is
    the mistake this fold exists to prevent twice over: per-card gaps overlap in an interleaved
    sitting, and two actors' streams must add (a card two agents worked in the same hour was
    attended twice). The grouping is HERE and not in the query it comes from: how this number is
    built is one decision, and a `GROUP BY` upstream would make storage the second place to know it.
    """
    streams: dict[str, list[tuple[float, str]]] = {}
    for task, actor, kind, ts in rows:
        if kind in WORK:
            streams.setdefault(actor, []).append((ts, task))
    out: dict[str, float] = {}
    for stream in streams.values():
        seconds, _ = _attribute(sorted(stream, key=lambda pair: pair[0]))
        for task, spent in seconds.items():
            out[task] = out.get(task, 0.0) + spent
    return out
