"""Decomposition: a whole plan — tasks, tree and DAG — created in one call.

One call and not N, because the graph is the point. An agent that creates five tasks
with five calls has to invent its own scheme for referring to the ones it just made, and
the dependencies land in a second pass a context limit can cut short. Here `after`
accepts the INDEX of an earlier entry in the same batch, so the plan arrives whole or not
at all.

taskops does not decompose anything itself. The session calling this already read the
code and thought about the work; asking a second model to re-derive that from a title
would be worse and slower. What this owns is that the result is persistent, ordered, and
legible to every other agent — including ones on other machines.

Field reading lives in `_entry`: this module builds a graph, that one decides what a
model meant by a field it spelled its own way.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from .._clock import now
from .._errors import BadRequest
from .._ids import new_task_id
from ..contracts import Dep, PlanResult, Task
from ..engine import record, unblock
from ..storage import Store
from . import _entry as field
from ._after import resolve_after
from ._project import caller, heartbeat, project
from ._routing import call_remote, whoami
from .acceptance import attach, criteria_in
from .reviewer import for_new

__all__ = ["plan"]


def plan(start: Path | str, entries: list[dict[str, Any]], *,
         actor: str = "") -> PlanResult:
    """Create every task in `entries`, wire the dependencies, return what unblocked."""
    if not entries:
        raise BadRequest("`tasks` is empty — a plan with no tasks is not a plan")
    if (answer := call_remote(start, "plan",
                              {"entries": entries, "actor": whoami(start, actor)})) is not None:
        return cast("PlanResult", answer)
    with project(start) as store:
        who = caller(store, actor)["id"]
        heartbeat(store, who)
        created = [_create(store, entry, who) for entry in entries]
        deps = _wire(store, entries, created)
        return PlanResult(created=created, deps=deps, unblocked=unblock(store))


def _create(store: Store, entry: dict[str, Any], who: str) -> Task:
    """One entry -> a stored task. Starts in `backlog`; `unblock` promotes it.

    Deliberately never created `ready`: whether a task is pickable is a property of the
    dependency graph, and letting a creator assert it directly is how the column starts
    disagreeing with the edges.
    """
    title = field.title_of(entry)
    if not title:
        raise BadRequest("every task needs a `title`")
    when = now()
    task = Task(id=new_task_id(), title=title,
                spec=str(entry.get("spec", "")).strip(), status="backlog",
                priority=field.priority_of(entry),
                parent=field.optional(entry, "parent"),
                labels=field.strings(entry, "labels"),
                files=field.strings(entry, "files"),
                created_by=who, assignee=field.optional(entry, "assignee") or "",
                # Resolved HERE and stored, so the card carries the answer: who may close it is
                # part of what was decided when the work was planned, not a lookup at close time.
                reviewer=for_new(store, field.stated(entry, "reviewer")),
                created=when, updated=when)
    store.tasks.insert(task)
    # The WHOLE task in the body, not just its title. The log is the source of truth another
    # machine rebuilds from, so an event that omits the spec is an event that cannot reconstruct
    # the task — which is exactly what happened: a teammate's `git pull` imported the events and
    # left them with an empty board. `engine.replay` is the reader.
    record(store, task=task["id"], actor=who, kind="created", body=_snapshot(task), ts=when)
    # Its own event, never a field of the snapshot: criteria are rewritten far more often than a
    # card is created, and one kind for "what this card promises" is what lets the latest
    # statement win without replay having to reason about a partially updated `created` body.
    attach(store, task["id"], criteria_in(entry.get("acceptance")), who)
    return task


def _snapshot(task: Task) -> dict[str, Any]:
    """Everything needed to recreate this task elsewhere. `id` and `created_by` are already on the
    event, so repeating them would be two places to keep in step."""
    return {"title": task["title"], "spec": task["spec"], "priority": task["priority"],
            "parent": task["parent"], "labels": task["labels"], "files": task["files"],
            "assignee": task["assignee"], "reviewer": task["reviewer"]}


def _wire(store: Store, entries: list[dict[str, Any]],
          created: list[Task]) -> list[Dep]:
    """Resolve every `after` into an edge: an index means this batch, a string an id."""
    out: list[Dep] = []
    # strict=True asserts the invariant rather than trusting it: `created` is built one
    # per entry, so a length mismatch means `_create` skipped one — and the symptom
    # would be a dependency wired to the WRONG task.
    for entry, task in zip(entries, created, strict=True):
        for reference in field.references(entry):
            out.append(_edge(store, resolve_after(store, reference, created),
                             task["id"], task["created_by"]))
        for waiting in field.blocked_ids(entry):
            # The INVERSE direction: this new card blocks an existing one. Same edge, other way
            # round, which is what makes the stuck-agent flow a single call.
            store.tasks.need(waiting)
            out.append(_edge(store, task["id"], waiting, task["created_by"]))
    return out


def _edge(store: Store, blocker: str, waiting: str, who: str) -> Dep:
    """One dependency, stored AND recorded.

    Recorded because a dependency that exists only in this machine's database is one a teammate's
    scheduler will walk somebody straight into after a `git pull`.
    """
    store.deps.add(blocker, waiting)
    record(store, task=waiting, actor=who, kind="blocked", body={"on": blocker})
    return Dep(task=blocker, blocks=waiting)
