"""Choosing what is in force, and which of it applies to one card. The slice IS the point.

Handing a worker the whole context book reproduces the problem the context layer exists to
solve — past ~150-200 standing instructions compliance decays, so a book that grows makes
every agent slightly worse. A slice is a card plus exactly the facts that bear on it.

Pure: facts in, facts out, no store. That is what makes the two rules below testable from
literals — every invariant survives the filter, and a tie between two machines resolves the
same way on both.
"""

from __future__ import annotations

from ..contracts import Task
from ..contracts.context import ContextSlice, Fact

__all__ = ["in_force", "for_task"]


def in_force(live: list[Fact]) -> ContextSlice:
    """The whole context as it stands: one objective, every invariant, every decision."""
    return ContextSlice(objective=winner([f for f in live if f["sort"] == "objective"]),
                        invariants=[f for f in live if f["sort"] == "invariant"],
                        decisions=[f for f in live if f["sort"] == "decision"])


def for_task(live: list[Fact], task: Task) -> ContextSlice:
    """The slice for one card: the same objective and invariants, only the decisions that
    touch its labels or its edit surface.

    Invariants are NOT filtered, and that is the load-bearing asymmetry. A decision that does
    not reach a card costs a re-litigation; an invariant that does not reach it costs the
    breakage it existed to prevent — so scope narrows decisions and never invariants.
    """
    whole = in_force(live)
    whole["decisions"] = [d for d in whole["decisions"] if _applies(d, task)]
    return whole


def winner(objectives: list[Fact]) -> Fact | None:
    """The current objective: the latest by `(ts, id)`.

    The tiebreak is the point, not the decoration. Two machines adding an objective offline
    can produce the same timestamp, and `id` is the CONTENT hash — identical on both — so
    both clones elect the same winner without talking. Comparing on arrival order instead
    would give each machine its own answer, which is a split brain nobody would notice.
    """
    return max(objectives, key=lambda f: (f["ts"], f["id"]), default=None)


def _applies(fact: Fact, task: Task) -> bool:
    """Unscoped facts reach everything; scoped ones reach what they overlap."""
    if not fact["labels"] and not fact["files"]:
        return True
    if set(fact["labels"]) & set(task["labels"]):
        return True
    return any(_touches(theirs, mine) for theirs in fact["files"] for mine in task["files"])


def _touches(one: str, other: str) -> bool:
    """Path overlap, either direction: a decision about `src/taskops/storage/` applies to a
    card editing one file in it, and a decision about that file applies to a card that owns
    the directory. String prefixes and not `Path.is_relative_to`, because these are repo
    paths written by hand and normalising them would invent a filesystem that may not exist.
    """
    left, right = one.rstrip("/"), other.rstrip("/")
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")
