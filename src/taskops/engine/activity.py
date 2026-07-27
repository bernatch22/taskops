"""The state of the WORKERS: what happened in a window, and who is live right now.

Both projections read events and leases, where `project` reads tasks and deps. The
seam is deliberate: how liveness is judged changes often (a grace period, a new
activity source) and how a board is drawn should not move when it does.
"""

from __future__ import annotations

from .._clock import HEARTBEAT_GRACE, now
from ..contracts import Event, Fleet, FleetMember, Lease, Standup, Task
from ..storage import Store

__all__ = ["standup", "fleet"]

_IN_FLIGHT = ("claimed", "in_progress", "review")


def standup(store: Store, *, since: float, actor: str = "") -> Standup:
    """What changed in a window. The auto-generated status report.

    Derived from EVENTS rather than from task rows, so it reports what happened
    instead of only where things landed: a task claimed, worked on and handed back
    shows its whole arc, where a row-based report would show it as untouched.
    """
    events = [e for e in store.events.since(since)
              if not actor or e["actor"] == actor]
    touched = _tasks_of(store, [e["task"] for e in events])
    return Standup(repo=str(store.root), since=since,
                   actors=sorted({e["actor"] for e in events}), events=events,
                   done=[t for t in touched if t["status"] == "done"],
                   in_flight=[t for t in touched if t["status"] in _IN_FLIGHT],
                   blocked=[t for t in touched if t["status"] == "blocked"])


def _tasks_of(store: Store, ids: list[str]) -> list[Task]:
    """The tasks those events were about, deduplicated, missing ones dropped.

    Dropped rather than reported: an event can legitimately name a task this machine
    has not pulled yet, and a standup is not where a sync gap gets explained.
    """
    out: list[Task] = []
    for task_id in dict.fromkeys(ids):
        found = store.tasks.get(task_id)
        if found is not None:
            out.append(found)
    return out


def fleet(store: Store, *, at: float | None = None) -> Fleet:
    """Who is working right now, and on what.

    Every live lease appears, including the ones this view no longer believes: an
    agent whose signal went quiet past the grace period still holds its claim, and a
    board that hid it would be hiding the exact row somebody needs to act on.
    """
    when = now() if at is None else at
    doing = store.events.latest_by_task("activity")
    return Fleet(repo=str(store.root),
                 members=[_member(lease, doing.get(lease["task"]), when)
                          for lease in store.leases.live(when)])


def _member(lease: Lease, activity: Event | None, when: float) -> FleetMember:
    """One live session. `last_seen` falls back to the CLAIM, not to zero.

    An agent whose hooks are not installed reports no activity at all, and reading
    that as "last seen at the epoch" would mark every such session dead — which is
    every session running plain Claude Code without the plugin.
    """
    last_seen = activity["ts"] if activity else lease["acquired"]
    summary = activity["body"].get("summary", "") if activity else ""
    return FleetMember(actor=lease["actor"], session=lease["session"],
                       task=lease["task"], branch=lease["branch"],
                       alive=(when - last_seen) < HEARTBEAT_GRACE,
                       last_seen=last_seen, doing=str(summary))
