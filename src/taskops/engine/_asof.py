"""The status a card held at a PAST moment, rebuilt from the log alone.

A window is a claim about the past, so the only status a dossier may sort a card by is the one
the card held inside that window. Reading today's status instead is what made regeneration
lossy: `opened_cards` lost 2 of 2026-07-30's 5 planned cards on the axion board as they closed,
and `in_flight`/`blocked`/`waiting` had the same bug one section further down — a card claimed
on Tuesday and finished on Thursday was in no Tuesday section at all by Friday.

**This could not be written until `scheduler.unblock` recorded its moves.** It did not, so
`backlog` and `ready` had no history to read and the fix here would have been a projection
folding an incomplete log — a new way to be wrong, dressed as an answer. Order mattered.

WHAT IS AND IS NOT RECOVERABLE, because the distinction is the honest part:

- Fully recoverable: `claimed`, `review`, `blocked`, `done`, `cancelled`. Those have always been
  recorded, by `_transition.move`, `claim._take`, `_freeing.release_lease` and `sweep_dead`. So
  which SECTION a card belongs in is right for every window, including windows years old.
- Recoverable only from the fix onward: `backlog` against `ready`. Every promotion that already
  happened went unrecorded and is gone for good — events are facts about the past and none may
  be invented to paper over a missing one. A card promoted in that era reconstructs as
  `backlog`, the status its `created` event states.
- Which is a within-section error, and that is why it is tolerable: `waiting` holds `ready` AND
  `backlog`, so the card lands in the correct section either way. What can read wrong for an old
  window is the GLYPH beside it, never the membership.
"""

from __future__ import annotations

from .._types import Status
from ..contracts import Task
from ..storage import Store
from ._stated import SAYS_STATUS, stated_status

__all__ = ["status_at", "statuses_at"]

BIRTH: Status = "backlog"
"""Where a card starts, and the anchor when the log states nothing before the moment asked
about. Not a guess: `replay._create` inserts every arriving card as `backlog`, and `plan` writes
the same, so `backlog` is what the `created` event MEANS. `ready` is only ever reached through
`unblock`, which is now the recorded transition that gets a card out of here."""


def status_at(store: Store, task: Task, at: float) -> Status:
    """The status `task` held at `at` — the last thing the log said about it before then.

    Strictly BEFORE `at`, because `at` is a window's exclusive upper edge: an event stamped
    exactly there belongs to the next window, and counting it would let two consecutive dossiers
    each claim the same transition.

    Falls back to `BIRTH` and never to the card's status TODAY. Today's status is the very thing
    this exists to stop reading — a fallback to it would reintroduce the bug on exactly the
    cards whose history is thin, which are the ones nobody would check.
    """
    for event in reversed(store.events.of_task(task["id"], kinds=SAYS_STATUS)):
        if event["ts"] < at:
            said = stated_status(event)
            if said is not None:
                return said
    return BIRTH


def statuses_at(store: Store, tasks: list[Task], at: float) -> dict[str, Status]:
    """`status_at` for a whole window's worth of cards, by id.

    One indexed read per card rather than a fold over the entire log: a report covers the cards
    a window TOUCHED, which is tens on a day and hundreds on `report all`, while the log is
    tens of thousands of rows and mostly commits and heartbeats.
    """
    return {task["id"]: status_at(store, task, at) for task in tasks}
