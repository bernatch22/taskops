"""Events -> tasks and dependencies. What makes the log the source of truth rather than a diary.

Without this, importing another developer's log gave you their EVENTS and an empty board — which is
exactly what happened when the usage guide was followed end to end, and what the sync test missed by
asserting on the log file instead of on the board.

It lives in `engine` because every line is a decision: which events describe state, what to do when
two machines disagree, and what to ignore. `storage.sync` moves bytes; this decides what they mean.

**Additive and idempotent.** Replaying the same event twice must change nothing, because a `git pull`
can deliver the same log a second time and `taskops sync` is safe to run in a loop. Nothing here
deletes: an event that arrives for a task this machine has never seen creates it, and an event that
contradicts newer local state loses.
"""

from __future__ import annotations

from .._types import EDITABLE_FIELDS, Status
from ..contracts import Event, Task
from ..storage import Store

__all__ = ["apply", "REPLAYED"]

REPLAYED = ("created", "blocked", "status", "done", "edited")
"""The kinds that describe STATE. Everything else — comments, commits, activity — is history: worth
keeping and rendering, but it does not tell you what a task IS. Listing them positively rather than
skipping a blocklist means a new kind is inert here until somebody decides it should not be."""


def apply(store: Store, events: list[Event]) -> int:
    """Materialise state from events. Returns how many actually changed something."""
    changed = 0
    for event in events:
        if event["kind"] == "created":
            changed += int(_create(store, event))
        elif event["kind"] == "blocked":
            changed += int(_block(store, event))
        elif event["kind"] in ("status", "done"):
            changed += int(_status(store, event))
        elif event["kind"] == "edited":
            changed += int(_edited(store, event))
    return changed


def _edited(store: Store, event: Event) -> bool:
    """A rewritten title, spec or priority — newer-wins, exactly like `_status`.

    The SAME arbitrator (`event["ts"]` against `task["updated"]`) rather than a per-field
    clock: one `updated` column is what the row has, and a second timestamp per field would
    be a schema for a case — two people editing two different fields of one card within the
    same sync window — that a shared task list barely produces. What it costs is that the
    older edit loses even when it touched another field; both are in the log, so it is
    recoverable, which is the trade `_status` already makes.
    """
    task = store.tasks.get(event["task"])
    field = event["body"].get("field")
    value = event["body"].get("to")
    if task is None or not isinstance(field, str) or field not in EDITABLE_FIELDS:
        return False
    if not isinstance(value, int if field == "priority" else str) or isinstance(value, bool):
        return False
    if event["ts"] <= task["updated"] or task[field] == value:  # type: ignore[literal-required]
        return False
    store.tasks.set_field(event["task"], field, value, when=event["ts"])
    return True


def _create(store: Store, event: Event) -> bool:
    """A task this machine has not seen. Existing ones are left ALONE.

    Not upserted: a `created` event is a statement about the past, and re-applying it would undo
    every local edit made since — a teammate's clone would keep resetting a spec somebody improved.
    """
    if store.tasks.get(event["task"]) is not None:
        return False
    body = event["body"]
    store.tasks.insert(Task(
        id=event["task"], title=str(body.get("title", "(untitled)")),
        spec=str(body.get("spec", "")), status="backlog",
        priority=_int(body.get("priority"), 2), parent=_optional(body.get("parent")),
        labels=_strings(body.get("labels")), files=_strings(body.get("files")),
        created_by=event["actor"], assignee=str(body.get("assignee", "")),
        created=event["ts"], updated=event["ts"]))
    return True


def _block(store: Store, event: Event) -> bool:
    """A dependency edge. Idempotent at the table (`INSERT OR IGNORE`), so this only reports.

    The blocker may not exist here yet — events arrive in file order, and a plan's edges can precede
    the tasks they point at when two logs merge. The edge is added anyway: `deps` has no foreign key
    for exactly this reason, and `open_blockers_of` joins on `tasks`, so an edge to an unknown task
    simply does not block until that task shows up.
    """
    blocker = str(event["body"].get("on", ""))
    if not blocker or blocker == event["task"]:
        return False
    store.deps.add(blocker, event["task"])
    return True


def _status(store: Store, event: Event) -> bool:
    """A status change, applied only if it is NEWER than what this machine has.

    `updated` is the arbitrator, and it is a wall clock from another machine — so a badly skewed
    clock can win an argument it should have lost. That is the accepted cost of having no server:
    both edits are in the log either way, so the outcome is always recoverable, and the alternative
    (a vector clock per task) is a great deal of machinery for a case that is already rare.

    A lease is never replayed. Leases are live local state about a process on one machine, and
    importing one would mean claiming a task on behalf of an agent that is not running here.
    """
    task = store.tasks.get(event["task"])
    target = event["body"].get("to")
    if task is None or not isinstance(target, str) or target not in _STATUSES:
        return False
    if event["ts"] <= task["updated"]:
        return False
    store.tasks.set_status(event["task"], _as_status(target), when=event["ts"])
    return True


_STATUSES = frozenset({"backlog", "ready", "claimed", "in_progress", "blocked", "review",
                       "done", "cancelled"})


def _as_status(value: str) -> Status:
    return value          # type: ignore[return-value]


def _int(value: object, fallback: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else fallback


def _optional(value: object) -> str | None:
    return str(value) if isinstance(value, str) and value.strip() else None


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]        # type: ignore[misc]
