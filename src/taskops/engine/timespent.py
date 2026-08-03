"""The three ways a board reads time out of the log: per card for a person, per sitting, per card.

All three are the same measure (`_measure`) applied to a different grouping, and that is deliberate —
a profile row, a sitting row and a card's own total have to agree, so the arithmetic lives in one
place and none of these three owns it.
"""

from __future__ import annotations

from ..contracts import Event
from ..contracts.spent import Attended, Stretch
from ._measure import GAP, WORK, attribute, worked

__all__ = ["attended", "stretches", "per_card", "GAP", "WORK"]


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
    seconds, counts = attribute(
        sorted(((e["ts"], e["task"]) for e in worked(events)), key=lambda pair: pair[0]))
    out = [Attended(task=task, seconds=seconds.get(task, 0.0), events=n)
           for task, n in counts.items()]
    return sorted(out, key=lambda a: (-a["seconds"], -a["events"], a["task"]))


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
    """A run's span, and the minutes it spent on each of its cards.

    Attributed WITHIN the run, by the same rule as everywhere else, which is what makes a group
    self-consistent: no gap inside a sitting exceeds the cap, so the per-card minutes add up to the
    span exactly and a reader can check the rows against the header. Drawing each card's total for
    the whole period inside an eleven-minute group was how this was found — thirty-two minutes in a
    stretch of eleven.

    In the order the cards were first touched: the order somebody actually opened them, and the only
    ordering here that carries information.
    """
    stamps = [(event["ts"], event["task"]) for event in run]
    seconds, counts = attribute(stamps)
    order: list[str] = []
    for _, task in stamps:
        if task not in order:
            order.append(task)
    return Stretch(started=run[0]["ts"], ended=run[-1]["ts"], events=len(run),
                   spent=[Attended(task=task, seconds=seconds.get(task, 0.0),
                                   events=counts.get(task, 0)) for task in order])


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
        seconds, _ = attribute(sorted(stream, key=lambda pair: pair[0]))
        for task, spent in seconds.items():
            out[task] = out.get(task, 0.0) + spent
    return out
