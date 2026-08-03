"""What one plan entry's REFERENCE to another task means — for both kinds, in one place.

A batch says two different things about how its cards relate, and the contract keeps them
apart: `parent` is the TREE ("what is this part of"), `after` is the DAG ("what must happen
first"). Different questions, but they resolve a reference identically — *an index means this
batch, anything else is an id* — and that is why they live together here rather than in `plan`,
which creates cards and should not also be a resolver.

Was `_after`, and the rename is the fix: `after` accepted an index and `parent` did not, and
the mismatch was SILENT. `parent: 0`, in the same call that takes `after: 0`, was read as "not
a string", dropped to `None`, and the plan came back reporting three cards created with a tree
that did not exist. One resolver is what makes a second convention impossible to reinvent.

The whole module keeps one promise: **a reference never silently fails to apply.** A plan whose
edges quietly did not land looks finished, reads as wired on the board, and schedules as if it
were flat — three workers offered work that should have been sequential. That is the most
expensive way for a plan to be wrong, because nothing about it looks wrong.
"""

from __future__ import annotations

from .._errors import BadRequest
from ..contracts import Task
from ..storage import Store

__all__ = ["resolve_after", "resolve_parent"]


def resolve_after(store: Store, reference: object, created: list[Task]) -> str:
    """One `after` entry -> the id of the task it blocks on. Raises on anything else."""
    blocker = named("after", reference, [task["id"] for task in created])
    _exists(store, blocker, reference, len(created))
    return blocker


def resolve_parent(store: Store, reference: object, ids: list[str], mine: int) -> str | None:
    """One `parent` -> the id of the epic this card belongs to, or None when it named nobody.

    Resolved against ids MINTED BEFORE ANY INSERT, which is what lets an index work here at all:
    the parent goes into the `created` event, and an event is the log's final word — so fixing
    it in a second pass would leave the log describing a tree the board does not have.

    `mine` is this entry's own index, and the only cycle worth checking by hand: a card that is
    its own parent is an epic nothing can ever close, because it is always its own open subtask.
    """
    if reference is None or reference == "":
        return None
    parent = named("parent", reference, ids)
    if parent == ids[mine]:
        raise BadRequest(f"entry {mine} is its own `parent` — an epic that contains itself can "
                         f"never be closed, because it is always its own open subtask")
    if parent not in ids:
        _exists(store, parent, reference, len(ids))
    return parent


def named(field: str, reference: object, ids: list[str]) -> str:
    """An index means this batch, anything else is read as a task id.

    An out-of-range index is an ERROR, never a skipped reference. `bool` is rejected before
    `int` because `True == 1` would otherwise resolve to the first task in the batch.
    """
    if isinstance(reference, bool):
        raise BadRequest(f"`{field}` got {reference!r} — expected an index or a task id")
    if isinstance(reference, int):
        if not 0 <= reference < len(ids):
            raise BadRequest(f"`{field}` index {reference} is outside this batch of "
                             f"{len(ids)} — indexes are 0-based")
        return ids[reference]
    return str(reference)


def _exists(store: Store, wanted: str, wrote: object, size: int) -> None:
    """A reference naming a task nothing knows is refused, exactly as an out-of-range index is.

    The promise above held for indexes and broke for strings: anything not an int fell through
    to "it is an id", `deps` has no foreign key — deliberately, so a teammate's edge can arrive
    before the task it points at — and `open_blockers_of` JOINs on `tasks`, so an edge to a task
    that does not exist blocks nothing at all.

    Found by writing `after: "0,1"` in a plan, which is the shape `tasks add --after` takes on
    the command line. The board showed a card depending on something and offered it to three
    workers at once. The message names that case, because it is the one a model copying the
    CLI's idiom will write.
    """
    if store.tasks.get(wanted) is not None:
        return
    hint = (f" — for several, write a LIST: [0, 1]. `{wrote}` was read as one task id"
            if isinstance(wrote, str) and "," in wrote else "")
    raise BadRequest(f"{wanted!r} is not a task in this batch of {size} nor on this "
                     f"board{hint}")
