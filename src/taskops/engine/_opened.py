"""The cards a window OPENED — planned work, with the edges that say what can start.

Split from `day` for the same reason `_closed` is: assembling a card needs the graph, and the
module that describes a window should not also know how the `deps` table is read from both
ends.

This exists because a freshly planned project reported nothing at all. `in_flight` covers
`claimed`/`in_progress`/`review` and `blocked` covers `blocked`, so `backlog` and `ready` —
which is ALL planned-but-unstarted work — belonged to no section, and a day spent writing four
specs rendered as `0 closed · 0 in flight · 0 blocked` over three empty headings. The same
class of bug as a finished project answering `tasks list` with silence: a filter that describes
some states, and everything else falling through it.
"""

from __future__ import annotations

from ..contracts import Event, OpenedCard, Task
from ..storage import Store

__all__ = ["opened_cards", "waiting_tasks"]


def opened_cards(store: Store, events: list[Event]) -> list[OpenedCard]:
    """One card per `created` event in the window, oldest first.

    Created AND closed INSIDE the window is dropped: `closed` already tells that card's whole
    story with its commits and its conversation, and listing it here too would invite a reader
    to count it twice. A card this clone does not have is dropped as well, like everywhere else
    — an event can name a task that still lives in a teammate's log.

    **Closed LATER is not closed here.** This filtered on the card's status AS OF NOW, so a
    card planned on Tuesday and finished on Thursday vanished from Tuesday's dossier — it was
    no longer open, and Tuesday's `closed` never held it either, because it closed on Thursday.
    Regenerating an OLD day therefore reported less than the same day generated at the time, and
    the loss was silent and permanent: 2026-07-30 on the axion board went from `5 opened` to
    `3` to `2` on three successive regenerations as its cards closed, one line of the day's
    planning disappearing per close. A window is a claim about the past, so the only status this
    may read is what the window itself did — which is the set of `done` events inside it, the
    same set `closed_cards` renders from.

    The card is still printed with its status TODAY, and that is deliberate: a `✓ done` under
    `## Abierto` says "planned that day, since finished", which is a fact, whereas a status
    reconstructed as-of-then would be a guess — `scheduler.unblock` moves a card between
    `backlog` and `ready` without recording an event, so the log cannot rebuild those two.
    """
    closed_here = {event["task"] for event in events if event["kind"] == "done"}
    out: list[OpenedCard] = []
    for event in events:
        task = store.tasks.get(event["task"]) if event["kind"] == "created" else None
        if task is not None and task["id"] not in closed_here:
            out.append(OpenedCard(task=task,
                                  waiting_on=store.deps.open_blockers_of(task["id"]),
                                  blocking=store.deps.dependents_of(task["id"])))
    return out


def waiting_tasks(touched: list[Task], opened: list[OpenedCard]) -> list[Task]:
    """Open cards nobody has started — minus the ones this window created.

    Those are in `opened`, where they carry their dependencies as well, and a card printed in
    both sections reads as two cards to anybody scanning. So every open card the window touched
    appears exactly once, and which section it is in says whether it is new.
    """
    new = {card["task"]["id"] for card in opened}
    return [t for t in touched
            if t["status"] in ("ready", "backlog") and t["id"] not in new]
