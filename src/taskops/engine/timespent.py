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
from ..contracts.board import Attended

__all__ = ["attended", "GAP"]

GAP = 30 * 60.0
"""The most a single gap may contribute, in seconds.

Thirty minutes because of how the events actually arrive: an agent's calls on one card land seconds
to a few minutes apart, so a gap past half an hour is somebody having left rather than somebody
thinking. It is deliberately ONE number and not a per-kind table — a rule a reader can hold is worth
more here than a fit, since the output is a bound and not an estimate.
"""


def attended(events: list[Event]) -> list[Attended]:
    """One actor's events, folded to time per card. Longest first.

    The caller passes ONE actor's events — the split is the caller's, because `history.rolls` has
    already grouped them and grouping twice is how two answers about the same actor start to differ.

    Sorted by `ts` before subtracting, which is not defensive: a `git pull` merges two ends of a log,
    so events reach a clone out of order, and a fold that trusted arrival order would take a
    difference backwards and count nothing.
    """
    per: dict[str, list[float]] = {}
    for event in events:
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
