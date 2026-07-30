"""The committed log ↔ the local cache. Multi-developer sync with no server.

`.taskops/events.jsonl` is append-only text, one event per line, and it is
COMMITTED. That is the whole mechanism: two developers' agents converge by `git
pull`, because appending to different ends of a file is the one edit git merges
without help, and content-hash ids make importing the same event twice a no-op.

What this module deliberately does NOT do is decide what an event MEANS. It moves bytes; turning
events into tasks and dependencies is `engine.replay`, which is also where the one genuine conflict
— two machines changing a task's status — is settled by timestamp.

There are no conflicts in the LOG to resolve: events are facts about the past, so the union of two
logs is the correct log.

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

__all__ = ["export_events", "import_events", "all_events", "read_log", "event_from",
           "record_arrivals"]


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


def record_arrivals(root: Path, events: list[Event]) -> int:
    """Write events that arrived from a SERVER into this checkout's log. Returns how many.

    `relay` stores them marked exported, so `export_events` will never write them — correct,
    since echoing a server's events back at it is how a log doubles. The cost was that they
    reached the database and nothing else, which made `db.sqlite` the only copy of a remote
    project's board: deleting it, the documented way to repair a cache, emptied the board
    instead, and `taskops sync` rebuilt nothing because the log genuinely did not have them.

    That is also the stated architecture being broken — nothing may hold state that is not
    derived from the log — so the fix is to make the log true rather than to document the
    exception. It has the side effect the project wants anyway: a teammate who syncs by git
    now receives what the server knew.
    """
    shared = [event for event in events if event["kind"] not in LOCAL_ONLY_KINDS]
    if shared:
        _append(root / LOG_FILE, shared)
    return len(shared)


def _append(path: Path, events: list[Event]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, sort_keys=True,
                                    separators=(",", ":")) + "\n")


def import_events(store: Store) -> list[Event]:
    """Load the log into the cache. Returns the events that were NEW here.

    The events themselves and not a count, because the caller has to do something with them:
    materialising tasks from them is `engine.replay`'s job, and it must see exactly the new ones.
    Returning a number was the earlier signature, and it is how the board stayed empty after a
    teammate's `git pull` — the events arrived and nothing turned them into tasks.

    Reads the whole file every time. At tens of thousands of events that is a few milliseconds, and
    the alternative — a byte offset into a file `git pull` rewrites from the middle — is a cursor
    that silently skips a merge.
    """
    fresh: list[Event] = []
    for event in read_log(store.root):
        if store.events.append(event, exported=True):
            fresh.append(event)
    return fresh


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
    """One log line -> an Event, or None."""
    raw = line.strip()
    if not raw:
        return None
    try:
        parsed: Any = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return event_from(parsed)


def event_from(parsed: Any) -> Event | None:
    """One decoded JSON value -> an Event, or None when it cannot be one.

    Every field is coerced rather than trusted. The producer is another machine's
    taskops, possibly a newer one, and `json.loads` returns Any — so without this
    an unexpected type would flow into the database and fail later at a render.

    Split from `_parse` because the committed log is no longer the only way a foreign
    event arrives: `POST /api/sync` receives them already decoded. Two coercions in two
    modules is how the two paths would start disagreeing about what a valid event IS —
    and since the id is the content, disagreeing means forking history.
    """
    if not isinstance(parsed, dict):
        return None
    fields = cast("dict[str, Any]", parsed)
    if not fields.get("id") or not fields.get("kind"):
        return None
    return Event(id=str(fields["id"]), task=str(fields.get("task", "")),
                 actor=str(fields.get("actor", "")), kind=fields["kind"],
                 body=as_dict(json.dumps(fields.get("body", {}))),
                 ts=float(fields.get("ts", 0.0)))


def all_events(root: Path) -> list[Event]:
    """The whole log, for a caller that has to re-apply state rather than fill gaps.

    Separate from `import_events` because they answer different questions: that one says "what is
    new here", this one says "what does the log say" — and a cache being rebuilt from a deleted
    database needs the second, since by then nothing is new.
    """
    return list(read_log(root))
