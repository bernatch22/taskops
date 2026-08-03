"""Rows in, contracts out. The one place that knows a column is JSON.

`labels`, `files` and `body` are JSON text in SQLite and lists or dicts everywhere
else. Doing that conversion in each table object meant four places knowing which
columns are encoded, and the fourth one always forgets — so it happens here, and a
table's job shrinks to writing SQL.

A stored value that is not valid JSON DEGRADES to empty rather than raising: these
columns are also written by `sync` from a file another machine's taskops appended,
and one malformed line must not make the whole board unreadable. The event
`body` is the extreme case — a newer version writes shapes this one has not seen.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, cast

from ..contracts import Event, Lease, Task

__all__ = ["dumps", "as_list", "as_dict", "to_task", "to_lease", "to_event"]


def dumps(value: object) -> str:
    """Compact and key-sorted: the text is compared across machines during sync,
    so two equal values must serialize identically."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def as_list(raw: object) -> list[str]:
    parsed = _loads(raw)
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in cast("list[object]", parsed)]


def as_dict(raw: object) -> dict[str, Any]:
    parsed = _loads(raw)
    return cast("dict[str, Any]", parsed) if isinstance(parsed, dict) else {}


def _loads(raw: object) -> object:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def to_task(row: sqlite3.Row) -> Task:
    return Task(
        id=str(row["id"]),
        title=str(row["title"]),
        spec=str(row["spec"]),
        status=row["status"],
        priority=int(row["priority"]),
        # `or ""` for the third time and the third reason: every card planned before milestones
        # existed reads NULL here after the ALTER, and "" is exactly what those cards mean — no
        # chapter, grouped under "(sin milestone)". `str(None)` would invent a chapter id.
        milestone=str(row["milestone"] or ""),
        parent=str(row["parent"]) if row["parent"] else None,
        labels=as_list(row["labels"]),
        files=as_list(row["files"]),
        created_by=str(row["created_by"]),
        # `or ""` and not `str(...)`: a row that predates the column reads as NULL after the ALTER,
        # and `str(None)` would put the string "None" in it — an assignee nobody can be.
        assignee=str(row["assignee"] or ""),
        # Same `or ""` for the same reason: every card written before reviewers existed reads
        # NULL here, and "" is exactly what those cards meant — nobody named, today's rule.
        reviewer=str(row["reviewer"] or ""),
        created=float(row["created"]),
        updated=float(row["updated"]),
    )


def to_lease(row: sqlite3.Row) -> Lease:
    return Lease(
        task=str(row["task"]),
        actor=str(row["actor"]),
        session=str(row["session"]),
        branch=str(row["branch"]),
        acquired=float(row["acquired"]),
        expires=float(row["expires"]),
    )


def to_event(row: sqlite3.Row) -> Event:
    return Event(
        id=str(row["id"]),
        task=str(row["task"]),
        actor=str(row["actor"]),
        kind=row["kind"],
        body=as_dict(row["body"]),
        ts=float(row["ts"]),
    )
