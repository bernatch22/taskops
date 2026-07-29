"""Why there is nothing to claim. Prose with branches in it, kept out of the claim path.

Split from `claim` because the two answer different questions: that module decides what an agent GETS,
this one explains what it did not get. Every branch here exists because a specific unhelpful answer
sent an agent to ask a human when it could have acted:

- "nothing ready" → it asks a human. "waiting on tk-abc" → it goes and does tk-abc.
- "cannot claim" → it retries the same call. "assigned to agent:ana/w2" → it asks for its own.
"""

from __future__ import annotations

from ..engine import counts
from ..storage import Store

__all__ = ["why_nothing", "why_not_this"]


def why_nothing(store: Store, labels: tuple[str, ...], wanted: str, asker: str = "") -> str:
    """Why there is nothing to do. "Nothing ready" alone sends the agent to ask a
    human; told WHICH — all blocked, all taken, or genuinely finished — it can act."""
    if wanted:
        return why_not_this(store, wanted, asker)
    numbers = counts(store)
    if numbers["open"] == 0:
        return "nothing open — the project is finished, or nothing has been planned"
    if labels:
        return (f"no ready task carries {', '.join(labels)}. Drop the label filter, "
                f"or plan the work that is missing")
    if numbers["ready"] == 0 and numbers["blocked"]:
        return (f"{numbers['blocked']} task(s) are waiting on a dependency and "
                f"{numbers['working']} are in flight — unblocking one of those is "
                f"the useful move")
    return (f"every ready task was claimed by another agent in the last moment "
            f"({numbers['working']} in flight) — ask again")


def why_not_this(store: Store, wanted: str, asker: str = "") -> str:
    """Why THIS task cannot be claimed. Each status has a different useful answer.

    A blocked task names its blockers, because "not ready" alone sends the agent to a human when
    the actionable move is usually to go work on the blocker instead.
    """
    task = store.tasks.need(wanted)
    if task["status"] == "backlog":
        blockers = ", ".join(store.deps.open_blockers_of(wanted)) or "unresolved deps"
        return (f"{wanted} is waiting on {blockers} — finish those first, or claim one "
                f"of them with taskops_next")
    if task["status"] in ("done", "cancelled"):
        return f"{wanted} is already {task['status']} — nothing to do there"
    if task["assignee"] and task["assignee"] != asker:
        # Naming the actor first, and the pool second. A dispatched specialist that reads this
        # is USUALLY the assignee and simply did not pass its own id — it resolved to the
        # developer's. Sending it to the pool instead was watched happen: refused its own card,
        # it asked for anything, and an api specialist walked off with a frontend one.
        return (f"{wanted} is assigned to {task['assignee']} — if that is you, say so: "
                f"taskops_next task={wanted} actor={task['assignee']}. If it is not, "
                f"taskops_next with no task will give you something that is yours")
    return f"{wanted} is {task['status']}, held by someone else — read it with taskops_ask"
