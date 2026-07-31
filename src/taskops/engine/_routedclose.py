"""The closing rule about routing — one question, kept apart from the two modules it sits between.

`routereview` decides WHO owns a review; `_review` collects what `→ done` demands. This is the
sentence where they meet, and it lived in each of them in turn: both hit their line budget, which
is the invariant saying the same thing twice — a rule about ownership is not a rule about closing,
and neither module wants to be the home of the other's question.
"""

from __future__ import annotations

from ..contracts import Task
from .routereview import routed_elsewhere

__all__ = ["refuse_routed_close"]


def refuse_routed_close(task: Task, actor: str) -> str | None:
    """A routed review is CLOSED by the dev it went to, and by nobody else while it holds.

    The hole this fills was watched on a live board and is embarrassing the way real bugs are:
    routing guarded the CLAIM and left the CLOSE open, so the one door that decides anything
    had no lock on it. A card routed to one developer was closed by a second, with no claim at
    all — straight from `review` to `done` — because a `dev:` actor passes every other closing
    rule by design (a person reading the diff IS the review).

    It answers FIRST among the closing rules, because it is the most specific thing anybody can
    say: "somebody else is already on this" beats "a peer may close this".

    Stale routing does not refuse. The routing expires precisely so a card cannot die waiting on
    a developer who closed their laptop, and a rule that outlived it would resurrect that
    failure at the last door instead of the first.
    """
    if not routed_elsewhere(task, actor):
        return None
    return (f"{task['id']} is routed to {task['assignee']} for review — it is in their sweep "
            f"and in nobody else's. Leave it: closing work that was chosen for somebody else "
            f"is how two people review one card and one of them wastes the afternoon. If they "
            f"are gone the routing expires on its own and the card opens to everybody.")
