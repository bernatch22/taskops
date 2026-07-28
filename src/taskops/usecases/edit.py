"""`taskops tasks edit` — rewriting the card itself: its title, its spec, its priority.

Until this existed, a spec was whatever the planner typed at 9am and nothing could correct
it: an agent that read a brief which had since turned out to be wrong had no door back, and
the only workaround was cancelling the card and planning a new one, which threw away its
thread and its commits.

Separate from `update` on purpose. `update` moves a card through the state machine and talks
about the WORK; this rewrites what the work IS. They record different events, they answer to
different guards, and folding them together would put a spec rewrite behind the same lease
and transition checks that exist to protect a status.

**One event per field**, never one `edited` carrying three. Replay applies each event on its
own merits, so a body holding three fields would make the newer-wins rule all-or-nothing —
two people editing different fields of the same card would clobber each other instead of
converging on both edits.
"""

from __future__ import annotations

from pathlib import Path

from .._clock import now
from .._errors import BadRequest
from .._types import CLOSED_STATUSES
from ..contracts import EditResult, Task
from ..engine import record
from ..storage import Store
from ._project import caller, heartbeat, project

__all__ = ["edit"]

CLOSED_REFUSAL = "closed cards are history — open a new card referencing it"
"""Why a done or cancelled card is frozen. The log is what a standup, a report and a
teammate's clone read back; letting somebody rewrite the spec of work already delivered
would rewrite the record of what was delivered, which is the one thing this system exists
to keep honest."""


def edit(start: Path | str, task_id: str, *, title: str | None = None,
         spec: str | None = None, priority: int | None = None,
         actor: str = "") -> EditResult:
    """Apply whatever fields were passed, recording one `edited` event for each."""
    asked = {"title": title, "spec": spec, "priority": priority}
    wanted = {field: value for field, value in asked.items() if value is not None}
    if not wanted:
        raise BadRequest("nothing to edit — pass a `title`, a `spec` or a `priority`")
    with project(start) as store:
        who = caller(store, actor)["id"]
        heartbeat(store, who)
        task = store.tasks.need(task_id)
        if task["status"] in CLOSED_STATUSES:
            raise BadRequest(CLOSED_REFUSAL)
        changed = [f for f, value in wanted.items() if _apply(store, task, who, f, value)]
        return EditResult(task=store.tasks.need(task_id), changed=changed)


def _apply(store: Store, task: Task, who: str, field: str, value: object) -> bool:
    """Write one field, and say so in the log. A no-op edit records NOTHING.

    An event whose `from` equals its `to` is a lie about the card's history and, worse,
    bumps `updated` — which is the arbitrator replay uses, so a redundant edit on one
    machine would win an argument against a real edit on another.
    """
    before = task[field]                # type: ignore[literal-required]
    if before == value:
        return False
    store.tasks.set_field(task["id"], field, value, when=now())
    record(store, task=task["id"], actor=who, kind="edited",
           body={"field": field, "from": before, "to": value})
    return True
