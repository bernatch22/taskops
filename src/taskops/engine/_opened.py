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

from .._types import CLOSED_STATUSES
from ..contracts import Event, OpenedCard, Task
from ..storage import Store

__all__ = ["opened_cards", "waiting_tasks"]


def opened_cards(store: Store, events: list[Event]) -> list[OpenedCard]:
    """One card per `created` event in the window, oldest first, still open.

    Created AND closed inside the window means `closed` already tells the whole story with its
    commits and its conversation; listing it here too would invite a reader to count it twice.
    A card this clone does not have is dropped, like everywhere else — an event can name a task
    that still lives in a teammate's log.
    """
    out: list[OpenedCard] = []
    for event in events:
        task = store.tasks.get(event["task"]) if event["kind"] == "created" else None
        if task is not None and task["status"] not in CLOSED_STATUSES:
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
