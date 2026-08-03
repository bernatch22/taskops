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
from typing import cast

from .._clock import now
from .._errors import BadRequest
from .._types import CLOSED_STATUSES
from ..contracts import EditResult, Task
from ..engine import record
from ..storage import Store
from ._planinto import chapter_to_move_into
from ._project import caller, heartbeat, project
from ._routing import call_remote, whoami
from .acceptance import attach, criteria_in
from .reviewer import named

__all__ = ["edit"]

CLOSED_REFUSAL = "closed cards are history — open a new card referencing it"
"""Why a done or cancelled card is frozen. The log is what a standup, a report and a
teammate's clone read back; letting somebody rewrite the spec of work already delivered
would rewrite the record of what was delivered, which is the one thing this system exists
to keep honest.

`milestone` is exempt, and only it. Filing a card under a chapter does not change anything
about what was delivered — it records WHICH chapter it was delivered in, which is the one
question a closed card is asked afterwards. On a board that predates chapters that is the only
way its history can be filed at all: every closed card on it carries none, so a picker shows the
board's one chapter beside a bucket holding every card ever finished. Nothing can be invented
this way either — the chapter still has to exist and be active, and no status moves."""

FILING = "milestone"
"""The one field a closed card still accepts. Named rather than inlined because the refusal
above argues about exactly this distinction, and a reader checking the argument against the code
should land on one word in both places."""


def edit(start: Path | str, task_id: str, *, title: str | None = None,
         spec: str | None = None, priority: int | None = None, reviewer: str | None = None,
         milestone: str | None = None, acceptance: object = None,
         actor: str = "") -> EditResult:
    """Apply whatever fields were passed, recording one `edited` event for each.

    `acceptance` is not one of them. It is a LIST, not a column, so it is restated whole through
    its own event rather than diffed field-by-field — which is also why it may be set on a card
    whose other fields nobody wants to touch.

    `reviewer` is checked before anything is written — an unknown specialist here is a card
    nobody can ever close, so it is refused naming the ones the project has. `--reviewer ""`
    clears it, which is a real edit and not a way of saying nothing.

    `milestone` is checked the same way and by the module that owns the question, which is what
    makes it a MOVE rather than a relabel: the chapter has to exist and to be active, because a
    card sitting inside a chapter somebody already closed is work the record says was shipped.
    """
    asked = {"title": title, "spec": spec, "priority": priority, "reviewer": reviewer,
             "milestone": milestone}
    wanted = {field: value for field, value in asked.items() if value is not None}
    if not wanted and acceptance is None:
        raise BadRequest("nothing to edit — pass a `title`, a `spec`, a `priority`, "
                         "a `reviewer`, a `milestone` or `acceptance`")
    if (answer := call_remote(start, "edit", {
            "task": task_id, "title": title, "spec": spec, "priority": priority,
            "reviewer": reviewer, "milestone": milestone, "acceptance": acceptance,
            "actor": whoami(start, actor)})) is not None:
        return cast("EditResult", answer)
    with project(start) as store:
        who = caller(store, actor)["id"]
        heartbeat(store, who)
        task = store.tasks.need(task_id)
        if task["status"] in CLOSED_STATUSES and (set(wanted) - {FILING} or acceptance is not None):
            raise BadRequest(CLOSED_REFUSAL)
        if reviewer is not None:
            wanted["reviewer"] = named(store, reviewer)
        if milestone is not None:
            wanted["milestone"] = chapter_to_move_into(store, milestone)
        changed = [f for f, value in wanted.items() if _apply(store, task, who, f, value)]
        if attach(store, task_id, criteria_in(acceptance), who)["criteria"]:
            changed.append("acceptance")
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
