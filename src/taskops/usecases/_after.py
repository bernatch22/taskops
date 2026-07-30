"""What `after` MEANS — one entry's dependency reference turned into a real task id.

Split out of `plan` when validating those references pushed that module past its budget, and
the split reads true: `plan` creates cards, this decides what the graph between them is. They
are two jobs and only one of them is about the DAG.

The whole module exists to keep one promise: **a dependency never silently fails to apply.** A
plan whose edges quietly did not land looks finished, reads as wired on the board, and schedules
as if it were flat — three workers offered work that should have been sequential. That is the
most expensive way for a plan to be wrong, because nothing about it looks wrong.
"""

from __future__ import annotations

from .._errors import BadRequest
from ..contracts import Task
from ..storage import Store

__all__ = ["resolve_after"]


def resolve_after(store: Store, reference: object, created: list[Task]) -> str:
    """One `after` entry -> the id of the task it blocks on. Raises on anything else."""
    blocker = _named(reference, created)
    _exists(store, blocker, reference, created)
    return blocker


def _named(reference: object, created: list[Task]) -> str:
    """An index means this batch, anything else is read as a task id.

    An out-of-range index is an ERROR, never a skipped edge. `bool` is rejected before `int`
    because `True == 1` would otherwise resolve to the first task in the batch.
    """
    if isinstance(reference, bool):
        raise BadRequest(f"`after` got {reference!r} — expected an index or a task id")
    if isinstance(reference, int):
        if not 0 <= reference < len(created):
            raise BadRequest(f"`after` index {reference} is outside this batch of "
                             f"{len(created)} — indexes are 0-based")
        return created[reference]["id"]
    return str(reference)


def _exists(store: Store, blocker: str, wrote: object, created: list[Task]) -> None:
    """An `after` naming a task nothing knows is refused, exactly as an out-of-range index is.

    The promise above held for indexes and broke for strings: anything not an int fell through
    to "it is an id", `deps` has no foreign key — deliberately, so a teammate's edge can arrive
    before the task it points at — and `open_blockers_of` JOINs on `tasks`, so an edge to a task
    that does not exist blocks nothing at all.

    Found by writing `after: "0,1"` in a plan, which is the shape `tasks add --after` takes on
    the command line. The board showed a card depending on something and offered it to three
    workers at once. The message names that case, because it is the one a model copying the
    CLI's idiom will write.
    """
    if store.tasks.get(blocker) is not None:
        return
    hint = (f" — for several, write a LIST: \"after\": [0, 1]. `{wrote}` was read as one task id"
            if isinstance(wrote, str) and "," in wrote else "")
    raise BadRequest(f"`after` names {blocker!r}, which is not a task in this batch of "
                     f"{len(created)} nor on this board{hint}")
