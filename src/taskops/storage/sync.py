"""The committed log ↔ the local cache. Multi-developer sync with no server.

`.taskops/events.jsonl` is append-only text, one event per line, and it is
COMMITTED. That is the whole mechanism: two developers' agents converge by `git
pull`, because appending to different ends of a file is the one edit git merges
without help, and content-hash ids make importing the same event twice a no-op.

What this deliberately does NOT do is resolve conflicts, because there are none to
resolve: events are facts about the past, so the union of two logs IS the correct
log. The only derived value that can disagree is a task's current status, settled
by `updated` in `_tasks.upsert` — and recoverable either way, since both edits are
in the log.

`activity` never leaves the machine (`LOCAL_ONLY_KINDS`): it is a per-tool-call
heartbeat, and replicating it would add thousands of lines a day to a file whose
whole value is that a human can read its diff.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator, cast

from .._types import LOCAL_ONLY_KINDS
from ..contracts import Event
from ._rows import as_dict
from .locate import LOG_FILE
from .store import Store

__all__ = ["export_events", "import_events", "rebuild", "read_log"]


def export_events(store: Store, *, limit: int = 1000) -> int:
    """Append this machine's new events to the log. Returns how many were written.

    The file is opened per call and closed immediately: a long-lived handle would
    keep a deleted inode alive after a `git checkout` swapped the file, and every
    write after that would go somewhere nobody can read.
    """
    fresh = store.events.unexported(limit=limit)
    shared = [e for e in fresh if e["kind"] not in LOCAL_ONLY_KINDS]
    if shared:
        _append(store.root / LOG_FILE, shared)
    if fresh:
        # Local-only kinds are marked too, or every export re-scans every activity
        # event this machine has ever written.
        store.events.mark_exported([e["id"] for e in fresh])
    return len(shared)


def _append(path: Path, events: list[Event]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, sort_keys=True,
                                    separators=(",", ":")) + "\n")


def import_events(store: Store) -> int:
    """Load the log into the cache. Returns how many were NEW here.

    Reads the whole file every time. At tens of thousands of events that is a few
    milliseconds, and the alternative — a byte offset into a file `git pull`
    rewrites from the middle — is a cursor that silently skips a merge.
    """
    new = 0
    for event in read_log(store.root):
        if store.events.append(event, exported=True):
            new += 1
    return new


def read_log(root: Path) -> Iterator[Event]:
    """Every well-formed event in the log, in file order.

    A malformed line is SKIPPED, not fatal: this file is merged by git and written
    by however many taskops versions a team runs, and one bad line must not make
    the project unreadable. Nothing is lost silently — the line is still in git.
    """
    path = root / LOG_FILE
    if not path.is_file():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            event = _parse(line)
            if event is not None:
                yield event


def _parse(line: str) -> Event | None:
    """One log line -> an Event, or None.

    Every field is coerced rather than trusted. The producer is another machine's
    taskops, possibly a newer one, and `json.loads` returns Any — so without this
    an unexpected type would flow into the database and fail later at a render.
    """
    raw = line.strip()
    if not raw:
        return None
    try:
        parsed: Any = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    fields = cast("dict[str, Any]", parsed)
    if not fields.get("id") or not fields.get("kind"):
        return None
    return Event(id=str(fields["id"]), task=str(fields.get("task", "")),
                 actor=str(fields.get("actor", "")), kind=fields["kind"],
                 body=as_dict(json.dumps(fields.get("body", {}))),
                 ts=float(fields.get("ts", 0.0)))


def rebuild(store: Store) -> int:
    """Replay the log into the cache. The disaster-recovery path.

    Additive rather than truncate-and-replay: leases are live state the log does
    not describe, so wiping the cache would drop every agent's claim in order to
    rebuild rows the log can reconcile anyway.
    """
    return import_events(store)
