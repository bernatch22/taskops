"""The state of the WORK: the board, and the three numbers that summarise it.

Nothing here is stored. That is the property worth protecting — a new column or a
different count is a rendering change with no migration, and any number on screen
can be traced back to the rows that produced it.

Who is doing the work lives in `activity`: that reads events and leases, this reads
tasks and dependencies, and keeping them apart means a change to how liveness is
judged cannot break how a board is drawn.
"""

from __future__ import annotations

from .._clock import now
from .._types import CLOSED_STATUSES, OPEN_STATUSES, STATUSES, WORKING_STATUSES
from ..contracts import Board, Card, Column
from ..storage import Store
from ..storage.belonging import chapter_of, sole
from .timespent import per_card

__all__ = ["board", "counts"]


def board(store: Store) -> Board:
    """Every task, in columns, with the counts that make a card readable.

    The aggregates come from ONE query each (`count_by_task`, `live`) rather than
    three per task: that difference is what separates a board that is fine at fifty
    tasks from one that stalls at five hundred.
    """
    tasks = store.tasks.all()
    commits = store.events.count_by_task("commit")
    # One query, folded per card — the same bargain `count_by_task` makes. A card's time has to
    # travel WITH the card: read out of a profile's window instead, it would change depending on how
    # far back somebody happened to be looking.
    spent = per_card(store.events.stamps_by_task())
    live = {lease["task"]: lease for lease in store.leases.live(now())}
    # A card written before this board had chapters resolves to its only one — see
    # `storage.belonging.sole`. Done HERE and not at ingest because the card is older than the
    # chapter, so the column cannot be right at the moment it lands.
    only = sole(store)
    tasks = [{**task, "milestone": chapter_of(task, only)} for task in tasks]   # type: ignore[misc]
    cards = [Card(task=task, lease=live.get(task["id"]),
                  blocked_by=len(store.deps.open_blockers_of(task["id"])),
                  blocks=len(store.deps.dependents_of(task["id"])),
                  commits=commits.get(task["id"], 0),
                  seconds=spent.get(task["id"], 0.0))
             for task in tasks]
    columns = [Column(status=status,
                      cards=[c for c in cards if c["task"]["status"] == status])
               for status in STATUSES]
    return Board(repo=str(store.root), columns=columns,
                 ready=sum(1 for t in tasks if t["status"] == "ready"),
                 total=len(tasks))


def counts(store: Store) -> dict[str, int]:
    """Ready / working / blocked, and the open-closed split.

    `next` reports these when it has nothing to hand over, so "nothing ready" always
    arrives with a diagnosis: everything blocked reads differently from everything
    claimed, and only one of the two is worth waking a human for.
    """
    statuses = [task["status"] for task in store.tasks.all()]
    return {"ready": statuses.count("ready"),
            "working": sum(1 for s in statuses if s in WORKING_STATUSES),
            "blocked": sum(1 for s in statuses if s in ("blocked", "backlog")),
            "open": sum(1 for s in statuses if s in OPEN_STATUSES),
            "closed": sum(1 for s in statuses if s in CLOSED_STATUSES)}
