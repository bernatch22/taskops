"""The context verbs: state a fact, withdraw one, read what is in force, read what was.

Every write goes through `engine.record`, the same door `plan` and `update` use. There is no
second event path and no file of its own on purpose: as events, these facts replicate through
`git pull` with everything else, are content-hashed so importing them twice is a no-op, and
get their history for free. A `context.json` would have been a third of that and a merge
conflict every time two people edited it.

Nothing is ever deleted. `retire` appends an event that withdraws another, which is the honest
way for an append-only log to say "we stopped believing this" — and it is why `log` can still
show what we used to think while `show` no longer does.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from .._errors import BadRequest
from .._types import EventKind
from ..contracts import Task
from ..contracts.context import CONTEXT_KIND, CONTEXT_TASK, SORTS, ContextSlice, Fact
from ..engine import record
from ..storage.context import fact_of, facts
from ._contextslice import for_task, in_force
from ._project import caller, heartbeat, project

__all__ = ["state", "retire", "show", "history", "context_for"]

_KIND = cast("EventKind", CONTEXT_KIND)
"""`EventKind` is a Literal in layer 0 and this module may not widen it, so the cast names the
one place the new kind enters the log. Nothing validates kinds at runtime — a reader that does
not know one stores and forwards it untouched, which is what lets an older taskops on a
teammate's machine carry these events without understanding them."""


def state(start: Path | str, sort: str, text: str, *, labels: Sequence[str] = (),
          files: Sequence[str] = (), horizon: str = "", owner: str = "",
          actor: str = "") -> Fact:
    """Record one fact. An objective supersedes the previous one by being NEWER, not by
    touching it — the old one stays in the log, which is what `context log` reads."""
    if sort not in SORTS:
        raise BadRequest(f"`{sort}` is not a context fact — expected {', '.join(SORTS)}")
    if not text.strip():
        raise BadRequest(f"an {sort} needs text — a fact with no statement states nothing")
    body: dict[str, Any] = {"sort": sort, "text": text.strip(), "labels": list(labels),
                            "files": list(files), "horizon": horizon, "owner": owner}
    with project(start) as store:
        who = caller(store, actor)["id"]
        heartbeat(store, who)
        stated = fact_of(record(store, task=CONTEXT_TASK, actor=who, kind=_KIND, body=body))
        if stated is None:                      # unreachable: `sort` was checked above
            raise BadRequest(f"`{sort}` produced no fact")
        return stated


def retire(start: Path | str, fact_id: str, *, actor: str = "") -> Fact:
    """Withdraw a fact. It leaves `show` and stays in `log`, because there is no eraser."""
    with project(start) as store:
        known = {f["id"]: f for f in facts(store, retired=True)}
        if fact_id not in known:
            raise BadRequest(f"no context fact `{fact_id}` — `taskops context log` lists them")
        who = caller(store, actor)["id"]
        heartbeat(store, who)
        record(store, task=CONTEXT_TASK, actor=who, kind=_KIND, body={"retires": fact_id})
        return {**known[fact_id], "retired": True}


def show(start: Path | str) -> ContextSlice:
    """What is in force, project-wide."""
    with project(start) as store:
        return in_force(facts(store))


def history(start: Path | str) -> list[Fact]:
    """Everything ever stated, retired ones included and marked."""
    with project(start) as store:
        return facts(store, retired=True)


def context_for(start: Path | str, task_id: str) -> ContextSlice:
    """The slice one card gets: every invariant, the current objective, and the decisions
    that match its labels or its files. This is what a worker is handed instead of the book."""
    with project(start) as store:
        task: Task = store.tasks.need(task_id)
        return for_task(facts(store), task)
