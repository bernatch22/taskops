"""How long an actor was ON a card, measured from the log and bounded from below.

Nothing records when somebody stopped working. What the log has is WHEN each thing happened, so the
only defensible answer is built out of the gaps between one actor's consecutive events on one card —
and every gap is capped before it is added.

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

__all__ = ["attended", "stretches", "on_card", "per_card", "worked", "GAP", "WORK"]

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

    Sorted by `ts` before subtracting, which is not defensive: a `git pull` merges two ends of a log,
    so events reach a clone out of order, and a fold that trusted arrival order would take a
    difference backwards and count nothing.
    """
    per: dict[str, list[float]] = {}
    for event in worked(events):
        per.setdefault(event["task"], []).append(event["ts"])
    out = [_one(task, sorted(stamps)) for task, stamps in per.items()]
    return sorted(out, key=lambda a: (-a["seconds"], -a["events"], a["task"]))


def _one(task: str, stamps: list[float]) -> Attended:
    """A card's total. ONE event scores zero seconds, and that is the honest answer: a single event
    is a moment, and there is no span between it and nothing. A floor here would be the invention
    the cap exists to avoid, multiplied by every card somebody touched once."""
    # `strict=False` because the pairing is deliberately ragged: a list zipped against itself
    # offset by one is n-1 pairs, and the last stamp has no successor to be paired with.
    seconds = sum(min(later - earlier, GAP) for earlier, later in zip(stamps, stamps[1:], strict=False))
    return Attended(task=task, seconds=seconds, events=len(stamps))


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


def on_card(stamps: list[tuple[str, str, float]]) -> float:
    """One CARD's attended time, over every actor that ever touched it. Seconds, a floor.

    Summed PER ACTOR and then added, which is the whole of the arithmetic and the one thing a naive
    version gets wrong: a card two agents worked in the same hour was attended twice, so the two
    stretches add. Subtracting consecutive events of the CARD instead would fold them into one and
    report half the work — the same mistake, mirrored, as billing a switch between two cards as time
    on both.

    Lives beside `attended` rather than in it because the question is the card's and not a person's:
    this is what a card carries wherever it is drawn, so it does not depend on which window somebody
    happens to be looking at a profile through.
    """
    per: dict[str, list[float]] = {}
    for actor, kind, ts in stamps:
        if kind in WORK:
            per.setdefault(actor, []).append(ts)
    return sum(_one("", sorted(times))["seconds"] for times in per.values())


def per_card(rows: list[tuple[str, str, str, float]]) -> dict[str, float]:
    """Every card's attended time, from one flat read of the log. `(task, actor, kind, ts)` in.

    The grouping is HERE and not in the query it comes from: how this number is built is one
    decision, and a `GROUP BY` upstream would make the storage layer the second place that knows it.
    """
    per: dict[str, list[tuple[str, str, float]]] = {}
    for task, actor, kind, ts in rows:
        per.setdefault(task, []).append((actor, kind, ts))
    return {task: on_card(stamps) for task, stamps in per.items()}
