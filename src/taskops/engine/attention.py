"""The board's open questions, in the order an orchestrator should answer them.

Every group here used to be an event pushed into a session through the channel. The rewrite is
the whole design note in one line: **the reaction to each of those events was idempotent and
derivable from state**, so a session that sweeps when it wakes reaches the same board as a
session that was interrupted the instant something moved — and it does it with no websocket, no
resident UI, and no notification that arrives one second after the return value said the same
thing.

What this REFUSES to include is as load-bearing as what it includes: a card being worked on
right now is not waiting for anybody. A sweep that listed everything in flight would be a board
dump with a verb on it, and an orchestrator that acts on it re-dispatches work already running.
So every group here is a card where **nothing will happen until somebody decides something**.
"""

from __future__ import annotations

from .._clock import now
from ..contracts import Task
from ..contracts.attention import MOVES, Waiting
from ..storage import Store

__all__ = ["waiting_on"]


def waiting_on(store: Store, *, at: float | None = None) -> list[Waiting]:
    """Every card that needs a decision, best move first. Reads only; decides nothing."""
    when = now() if at is None else at
    held = {lease["task"] for lease in store.leases.live(when)}
    found = [item for task in store.tasks.all()
             if (item := _move(store, task, held)) is not None]
    # Priority ASCENDING, like `scheduler.score` — 0 is urgent here and 3 is "whenever", so a
    # descending sort recommends the least urgent work first. It did, from the day this was
    # written until a priority-0 card landed on a live board and sorted below eight priority-2
    # ones. The one direction nobody checks is the one where every card has the same priority.
    return sorted(found, key=lambda item: (MOVES.index(item["move"]),
                                           item["task"]["priority"], item["task"]["updated"]))


def _move(store: Store, task: Task, held: set[str]) -> Waiting | None:
    """The ONE next move on one card, or None when it is somebody's turn already.

    A lease short-circuits everything EXCEPT what `_declared` answers first: an agent alive on
    a card and reporting owns the next move on it, whatever the board would otherwise say. That
    is the check keeping a sweep from handing a live card to a second worker.
    """
    if task["status"] in ("done", "cancelled"):
        return None
    if (declared := _declared(store, task, held)) is not None:
        return declared
    if task["id"] in held:
        return None
    if task["assignee"]:
        # Assigned, no lease: a bounce back from review, or a dispatch nobody spawned. Either
        # way the card is INVISIBLE to every other agent — assignment is what hides it — so it
        # sits here forever unless the worker it names is started again.
        return _at(task, "resume", f"assigned to {task['assignee']}, which is not running")
    if task["status"] != "ready":
        return None
    if not task["spec"].strip():
        return _at(task, "specless", "ready with no spec — a worker can only guess at it")
    return _at(task, "dispatch", "ready, unassigned, and nothing depends on it first")


def _declared(store: Store, task: Task, held: set[str]) -> Waiting | None:
    """The two statuses the lease does not simply veto, because each means something extra.

    `blocked` keeps its lease and is judged AS IF it had none: only `ready`, `review`, `done`
    and `cancelled` release one, so a worker that had just declared itself blocked went on
    looking busy for the fifteen minutes until the TTL ran out. Its own declaration is the
    better evidence — an agent saying "I am blocked on this" is saying it is not working on it.

    `review` reads the lease the other way round: the handover RELEASED it everywhere (the
    mirror included, since `LEASE_ENDS` became one list), so a LIVE lease on a review card now
    has exactly one meaning — a verifier claimed it and is checking right now. That lease is
    what ended triple verification: one real card was verified three times in parallel, each
    run building its own venv, because a review card appeared in every session's sweep at once.
    """
    if task["status"] == "blocked":
        return _stalled(store, task)
    if task["status"] != "review":
        return None
    if task["id"] in held:
        return None          # a verifier holds it — it is that verifier's turn, not yours
    who = task["reviewer"] or "the verifier"
    return _at(task, "verify", f"in review since it was handed over; {who} has not closed it")


def _stalled(store: Store, task: Task) -> Waiting:
    """`blocked` is the one status NOTHING in this system ever moves a card out of.

    Written after checking, because the obvious version of this was wrong: a *dependency* going
    dead is not the dead end it looks like — `unblock` counts `cancelled` as closed and frees
    the card the next time anything runs. The real hole is one status up. `unblock` only ever
    scans `backlog` and `ready`, so a card an agent parked with `blocked_on` sits there until a
    person moves it, and on a board it reads exactly like a card somebody is working on.

    That is the failure this project named "never leave a story dead", and it is the only one
    of these groups where the sweep is telling you about work that already stopped.
    """
    open_blockers = store.deps.open_blockers_of(task["id"])
    waiting_for = f"blocked on {', '.join(open_blockers)}" if open_blockers else (
        "blocked with nothing open to wait for")
    return _at(task, "stalled", f"{waiting_for} — nothing frees a `blocked` card but a person")


def _at(task: Task, move: str, why: str) -> Waiting:
    return Waiting(task=task, move=move, why=why)      # type: ignore[typeddict-item]
