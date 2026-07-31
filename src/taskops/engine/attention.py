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
from ._peer import reviewer_is_a_peer
from ._peerfacts import facts_of
from .routereview import routed_elsewhere

__all__ = ["waiting_on"]


def waiting_on(store: Store, *, at: float | None = None, actor: str = "") -> list[Waiting]:
    """Every card that needs a decision, best move first. Reads only; decides nothing.

    `actor` narrows VERIFY to the reviews this caller could actually close. Without it the
    sweep told a developer to verify eleven cards their own agents had written, on a board
    whose `reviewer: peer` decision forbids exactly that — six refused calls before the model
    worked out that the rule is per TEAM, not per session. Advice that the engine will refuse
    is worse than no advice: it costs calls and teaches the reader to distrust the list.
    """
    when = now() if at is None else at
    held = {lease["task"] for lease in store.leases.live(when)}
    found = [item for task in store.tasks.all()
             if (item := _move(store, task, held)) is not None
             and not _refused(store, item, actor)]
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
    if task["status"] == "cancelled":
        return None
    if task["status"] == "done":
        return _unlanded(store, task)
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


def _refused(store: Store, item: Waiting, actor: str) -> bool:
    """Would the close guard refuse this caller outright? Then it is not their move.

    Only VERIFY, and only for a reason that cannot change by trying: `reviewer: peer` on work
    this actor's own dev produced. Everything else a caller might fail at — no commit, missing
    evidence, an open child — is fixable BY the caller, so listing it is the point.
    """
    if not actor or item["move"] != "verify":
        return False
    # Routed, and not to you: hidden. Showing it IS the broadcast this design buried — two
    # free developers starting the same review because both were told. Stale routing reopens it.
    if routed_elsewhere(item["task"], actor):
        return True
    return bool(reviewer_is_a_peer(facts_of(store, item["task"], actor)))


def _unlanded(store: Store, task: Task) -> Waiting | None:
    """A closed card whose branch never reached the trunk.

    The ONLY reason a `done` card appears in a sweep, and it earned its place: a board once
    reported a hundred and eighteen cards done with the trunk still on its seed commit, and a
    hundred and thirty-three branches nobody had merged. `done` used to mean two things — "I
    finished" and "this is in the trunk" — and only the first was ever true.

    Silent for a card that never carried code (`no_code`, or a card whose landing succeeded),
    and silent for every card closed before landing existed: no `landed` event at all means
    this board predates the feature, and filling a sweep with history helps nobody.
    """
    events = store.events.of_task(task["id"], kinds=("landed",))
    if not events or events[-1]["body"].get("ok"):
        return None
    why = str(events[-1]["body"].get("why") or "it did not merge")
    return _at(task, "land", f"closed but not in the trunk — {why}")


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
