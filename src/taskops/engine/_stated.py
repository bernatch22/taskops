"""What one event SAYS about a card's status — the single reading of that question.

Extracted from `replay`, which used to own it alone, the moment a second reader appeared:
`_asof` rebuilds the status a card held at a past moment, and that is the same question asked
about a different clock. Two copies of "a `claimed` means claimed, an `in_progress` means
claimed" is how one of them learns about a new kind and the other does not — and the two
readers here are the board's present state and every dossier ever regenerated, so a drift
between them would render as history disagreeing with itself.

Says NOTHING about whether the statement should be applied. Arbitration against what a machine
already has belongs to `replay`; a window's boundary belongs to `_asof`.
"""

from __future__ import annotations

from .._types import STATUSES, Status
from ..contracts import Event

__all__ = ["SAYS_STATUS", "stated_status"]

SAYS_STATUS: tuple[str, ...] = ("status", "done", "claimed", "released")
"""The kinds that STATE a status. A subset of `replay.REPLAYED`, which also carries `created`
and `blocked` and `edited` — those describe a card or an edge, not where it is.

`blocked` is the trap and it is worth naming: the KIND means a dependency edge was added, not
that the card reached the `blocked` status. A reader that took the kind for the status would
report every card that ever gained a blocker as blocked on the day it did."""

_IMPLIED: dict[str, str] = {"claimed": "claimed", "released": "ready", "done": "done"}
"""What a kind says when the body does not. `claimed` and `released` predate `status` events and
their bodies carry a session and a branch instead of a target, so the kind IS the statement."""

_RETIRED: dict[str, str] = {"in_progress": "claimed"}
"""Retired statuses map to what they always meant. Neither reader may ever refuse history: a
teammate's log still carries `in_progress`, and so does every dossier's worth of past."""


def stated_status(event: Event) -> Status | None:
    """The status this event states, or None if it states none.

    None rather than a raise for an unknown value: a log written by a NEWER taskops can name a
    status this one has never heard of, and the honest answer to "what did it say" is then "I
    cannot tell", not a crash in the middle of somebody's report.
    """
    if event["kind"] not in SAYS_STATUS:
        return None
    stated = event["body"].get("to", _IMPLIED.get(event["kind"]))
    target = _RETIRED.get(stated, stated) if isinstance(stated, str) else stated
    if not isinstance(target, str) or target not in STATUSES:
        return None
    return target       # type: ignore[return-value]
