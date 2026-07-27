"""Assembling everything about one task — the read `ask` and `next` both return.

One function, because both callers need the same thing and an agent that had to make
five calls to learn a task's context would make three of them and start on a stale
picture. The expensive part is `neighbours`: the tasks whose `files` overlap this one's,
which is the collision warning an agent can act on BEFORE it edits rather than after
the merge.
"""

from __future__ import annotations

from .._clock import now
from ..contracts import Event, Inbox, Task, TaskView
from ..storage import Store

__all__ = ["view", "inbox_for", "THREAD_KINDS"]

THREAD_KINDS = ("comment", "message", "handoff")
"""What counts as conversation. `status` and `commit` events are history, not talk —
mixing them would bury four sentences of reasoning under forty state changes."""


def view(store: Store, task_id: str) -> TaskView:
    """A task and its whole context. Raises if the id does not exist."""
    task = store.tasks.need(task_id)
    history = store.events.of_task(task_id)
    return TaskView(
        task=task, lease=store.leases.get(task_id),
        blocked_by=_tasks(store, store.deps.open_blockers_of(task_id)),
        blocks=_tasks(store, store.deps.dependents_of(task_id)),
        children=store.tasks.children(task_id),
        neighbours=_neighbours(store, task),
        thread=[e for e in history if e["kind"] in THREAD_KINDS],
        commits=[str(e["body"].get("sha", "")) for e in history
                 if e["kind"] == "commit"],
        history=history)


def _tasks(store: Store, ids: list[str]) -> list[Task]:
    """Ids -> tasks, dropping any this machine has not pulled yet.

    Dropped rather than raised: a dependency can legitimately name a task that is in
    a teammate's log and not yet in this clone, and refusing to render the task in
    front of us because of it would make a sync gap look like data loss.
    """
    out: list[Task] = []
    for task_id in ids:
        found = store.tasks.get(task_id)
        if found is not None:
            out.append(found)
    return out


def _neighbours(store: Store, task: Task) -> list[Task]:
    """Open tasks that touch at least one of the same files.

    A linear scan over open tasks. At the scale of a task list that is nothing, and
    an inverted index on `files` would be a second structure to keep correct for a
    read that is already cheap.
    """
    mine = set(task["files"])
    if not mine:
        return []
    return [other for other in store.tasks.with_status(
                ("ready", "claimed", "in_progress", "review", "blocked"))
            if other["id"] != task["id"] and mine & set(other["files"])]


def inbox_for(store: Store, actor: str, *, mark: bool = True, limit: int = 50) -> Inbox:
    """What this actor has not been shown, and by default mark it shown.

    `mark=False` exists for the studio: a human glancing at a board must not consume
    an agent's messages. Delivery is a fact about the AGENT having seen something,
    and only the agent's own read may assert it.
    """
    pending = store.delivered.pending(actor, limit=limit)
    if mark and pending:
        store.delivered.mark(actor, [e["id"] for e in pending], when=now())
    return Inbox(actor=actor, messages=pending,
                 tasks=list(dict.fromkeys(e["task"] for e in pending)))


def empty_inbox(actor: str) -> Inbox:
    """The no-messages case, so callers never branch on None."""
    return Inbox(actor=actor, messages=[], tasks=[])


def thread_of(history: list[Event]) -> list[Event]:
    """The conversation out of a history. Exposed for the renderers, which are
    handed events and must not re-decide what a conversation is."""
    return [event for event in history if event["kind"] in THREAD_KINDS]
