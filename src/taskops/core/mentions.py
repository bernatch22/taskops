"""Who was addressed and has not answered — derived, never a stored flag.

A mention is not a new event kind: it is an extra `mentions` key on a `comment`
body, which `event.make()` already keeps intact. Writing one is the easy half.
The hard half is knowing whether it is still PENDING, and this project answers
"is that still true?" the same way every time (`graph.py`): compute it, never
write a second fact to contradict the first later.

    a mention of `actor` on a card is pending until `actor` writes ANY event
    on that card after it, or the card closes.

Answering clears it, taking the card clears it, closing it clears it — with no
`read` column, no `ack` verb and no sweep. That is the reasoning that killed
the `recover` verb: a flag exists only to contradict something that should have
been derived, and then somebody has to remember to write it. Ignored forever, a
mention stays pending forever, which is the correct behaviour and not a bug.
"""

from __future__ import annotations

from typing import Mapping, TypedDict, Collection

from .types import Event
from .._json import as_strings


class Mention(TypedDict):
    """One address nobody has answered. Computed on every read; never a row."""

    task: str
    by: str  # who wrote the comment, not who it is for
    text: str
    ts: float


def addressed(event: Event) -> list[str]:
    """The actors a `comment` names.

    Anything that is not a list of strings is nobody: the body is open by
    design (a newer writer's extra keys arrive intact), so a foreign shape has
    to read as "no mention", never as an exception in the middle of a board.
    """
    if event["kind"] != "comment":
        return []
    return as_strings(event["body"].get("mentions"))


def pending(
    threads: Mapping[str, list[Event]], actor: str, closed: Collection[str] = ()
) -> list[Mention]:
    """Every mention of `actor` with no later event from `actor` on that card.

    `closed` is the set of cards that are done or dropped, passed in rather
    than looked up — the same bargain `graph.Holders` makes, so this module
    stays pure. A closed card owes nobody a reply.

    Events are sorted by `ts` with Python's STABLE sort and compared by
    POSITION, not by timestamp: two events in the same second keep arrival
    order (`replay` settles simultaneity the same way), and "did they answer?"
    must not depend on which of the two happens to sort first.
    """
    out: list[Mention] = []
    for task, events in threads.items():
        if task in closed:
            continue
        ordered = sorted(events, key=lambda e: e["ts"])
        answered = _last_by(ordered, actor)
        for index, event in enumerate(ordered):
            if index < answered or actor not in addressed(event):
                continue
            out.append(
                Mention(
                    task=task,
                    by=event["actor"],
                    text=str(event["body"].get("text", "")),
                    ts=event["ts"],
                )
            )
    return sorted(out, key=lambda m: m["ts"])


def _last_by(ordered: list[Event], actor: str) -> int:
    """Index of the last event `actor` wrote, or -1 if it never spoke here.
    Everything before that index has been answered, by definition."""
    for index in range(len(ordered) - 1, -1, -1):
        if ordered[index]["actor"] == actor:
            return index
    return -1
