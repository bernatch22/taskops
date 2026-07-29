"""Gathering what the state machine is allowed to know.

`engine.machine` holds guards that are pure functions of `Facts`, which is what lets every rule be
tested from literals with no database. Something still has to READ those facts, and this is it — the
one place that turns a task plus a store plus git into the record the machine decides on.

Its own module because the reading is not the deciding. `update` orchestrates; the machine judges;
this fetches. When a guard needs a new fact, the change is one function here and one line there.
"""

from __future__ import annotations

from .._clock import now
from ..contracts import Task
from ..engine import Evidence, Facts, branch_state, open_children
from ..storage import Store
from .acceptance import criteria_of

__all__ = ["facts_for", "unpushed_on", "entered_review_by"]


def facts_for(store: Store, task: Task, actor: str, *, no_code: bool,
              justification: str, evidence: str = "", no_evidence: str = "") -> Facts:
    """Everything the guards may ask about, read once."""
    lease = store.leases.get(task["id"])
    return Facts(
        evidence=Evidence(criteria=tuple(criteria_of(store, task["id"])),
                          given=evidence, waived=no_evidence),
        task=task, actor=actor,
        has_live_lease=store.leases.held_by(task["id"], actor, now()),
        commits=len(store.events.of_task(task["id"], kinds=("commit",))),
        open_children=open_children(store, task["id"]),
        no_code=no_code, justification=justification, reviewer=str(task.get("reviewer", "")),
        entered_review_by=entered_review_by(store, task["id"]),
        unpushed=unpushed_on(store, lease["branch"] if lease else ""))


def entered_review_by(store: Store, task_id: str) -> str:
    """Who asked for the review, or "" if the card is not sitting in one.

    Derived from the LOG rather than from a column, deliberately. The events already answer
    "who moved this card where", so a `reviewer` column would be a second copy of that answer,
    written by one code path and able to disagree with the log the board is rebuilt from.

    It reads the LAST status event and only counts it when its target was `review`. That is
    what makes the rule self-clearing: a card bounced back to `in_progress` and finished has a
    newer status event, so the agent that once asked for a review may close it again — the
    refusal is about closing a review you opened, not about ever having opened one.
    """
    moves = store.events.of_task(task_id, kinds=("status",))
    last = moves[-1] if moves else None
    return str(last["actor"]) if last and last["body"].get("to") == "review" else ""


def unpushed_on(store: Store, branch: str) -> int:
    """Commits on this branch that no remote has. 0 when there is no branch or no remote.

    Read at CLOSE time rather than stored: it changes every time anybody pushes, so a cached answer
    would be wrong more often than right.

    A branch with no upstream returns 0 and not "everything", deliberately. Git has nothing to
    compare against there, so any number would be invented — and a solo developer with no remote at
    all would otherwise see every task reported as unpushed forever.
    """
    if not branch:
        return 0
    state = branch_state(store.root, branch)
    if not state["exists"] or not state["upstream"]:
        return 0
    return state["ahead"]
