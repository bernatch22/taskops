"""The status a card held at a past moment — and the BOUNDARY of what the log can answer.

Half of this file asserts a fix and half asserts a limit, deliberately. Every transition that
happened before `unblock` began recording is gone for good, and a projection that quietly papered
over that would be the same failure as the one it replaces: a report mixing reconstructed history
with present state, which is exactly what nobody could detect the first time.
"""

from __future__ import annotations

from taskops.contracts import Task
from taskops.engine import record
from taskops.engine._asof import BIRTH, status_at
from taskops.engine._stated import stated_status
from taskops.storage import Store

AT = 1_000_000.0


def _task(store: Store, task_id: str, status: str = "ready") -> Task:
    task = Task(id=task_id, title=f"Work {task_id}", spec="", status=status, priority=2,
                milestone="", parent=None, labels=[], files=[], assignee="", reviewer="",
                created_by="dev:berna", created=1.0, updated=1.0)
    store.tasks.insert(task)
    return task


def _log(store: Store, task: str, kind: str, ts: float, **body: object) -> None:
    record(store, task=task, actor="dev:berna", kind=kind, body=body, ts=ts)


def test_the_last_thing_the_log_said_before_the_moment_wins(store: Store) -> None:
    task = _task(store, "tk-1", status="done")
    _log(store, "tk-1", "claimed", AT - 100.0, to="claimed")
    _log(store, "tk-1", "status", AT - 50.0, to="review")
    _log(store, "tk-1", "done", AT + 50.0, to="done")
    assert status_at(store, task, AT) == "review"


def test_the_moment_itself_is_EXCLUSIVE(store: Store) -> None:
    """`at` is a window's upper edge. An event stamped exactly there is the next window's, and
    counting it in both would let two consecutive dossiers each claim one transition."""
    task = _task(store, "tk-1", status="claimed")
    _log(store, "tk-1", "claimed", AT, to="claimed")
    assert status_at(store, task, AT) == BIRTH


def test_it_never_falls_back_to_the_status_the_card_holds_TODAY(store: Store) -> None:
    """The whole defect was reading the present. A fallback to it would put the bug back on
    precisely the cards whose history is thin — the ones nobody would think to check."""
    task = _task(store, "tk-1", status="done")
    assert task["status"] == "done"
    assert status_at(store, task, AT) == BIRTH


def test_a_dependency_edge_is_not_the_blocked_STATUS(store: Store) -> None:
    """Kind `blocked` means an edge was added. Reading the kind as the status would report every
    card that ever gained a blocker as blocked on the day it gained one."""
    task = _task(store, "tk-1", status="ready")
    _log(store, "tk-1", "blocked", AT - 10.0, on="tk-other")
    assert status_at(store, task, AT) == BIRTH
    assert stated_status(store.events.of_task("tk-1")[0]) is None


def test_a_retired_status_in_an_old_log_still_reads(store: Store) -> None:
    """`in_progress` was removed from the vocabulary and is still in real logs. Neither reader
    of the log may ever refuse history."""
    task = _task(store, "tk-1", status="done")
    _log(store, "tk-1", "status", AT - 10.0, to="in_progress")
    assert status_at(store, task, AT) == "claimed"


def test_a_status_from_a_NEWER_taskops_is_unreadable_rather_than_fatal(store: Store) -> None:
    """A log written by a version that knows a status this one does not. "I cannot tell" beats
    a crash in the middle of somebody's report."""
    task = _task(store, "tk-1", status="ready")
    _log(store, "tk-1", "status", AT - 10.0, to="marinating")
    assert status_at(store, task, AT) == BIRTH


def test_THE_BOUNDARY_a_promotion_never_recorded_reconstructs_as_backlog(store: Store) -> None:
    """What is NOT recoverable, pinned so nobody discovers it in a report instead.

    Before `unblock` recorded, a card promoted to `ready` left no trace. That fact is gone —
    events are facts about the past and none may be invented to fill a gap — so such a card
    reconstructs as `backlog`, which is what its `created` event states.

    Why it is tolerable, and the reason this card's second half was smaller than feared: the
    unrecorded transitions are only ever backlog↔ready, and the dossier's `waiting` section
    holds BOTH. So the card lands in the RIGHT section either way; what can read wrong for an
    old window is the glyph beside it. `test_day` asserts that section membership.
    """
    task = _task(store, "tk-1", status="ready")
    _log(store, "tk-1", "created", AT - 500.0, title="Work tk-1")     # a pre-fix card's whole log
    _log(store, "tk-1", "comment", AT - 100.0, text="still sitting in ready")

    assert status_at(store, task, AT) == "backlog", "the promotion was never written down"
    assert status_at(store, task, AT) in ("ready", "backlog"), "and both are one section"
