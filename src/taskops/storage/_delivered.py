"""Who has been shown what — the inbox's memory.

A per-pair table rather than a `last_seen` timestamp per actor. The reason is the
delivery path: an agent's messages reach it through whichever hook fires first, in
an order nobody controls, and events arrive from two replication paths with
timestamps set by two machines. A cursor would advance past a message that landed
a second late and that message would never be delivered — silently, which is the
worst way for a coordination system to fail.

The cost is one row per (actor, message). Bounded by conversation volume, not by
event volume: only directed kinds are ever tracked here.
"""

from __future__ import annotations

import sqlite3

from ..contracts import Event
from ._rows import to_event

__all__ = ["DeliveredTable"]


class DeliveredTable:
    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db

    def pending(self, actor: str, *, limit: int = 50) -> list[Event]:
        """Directed events this actor has not been shown, oldest first.

        "Directed at" is `mentions` containing the actor id, matched in SQL with a
        LIKE over the JSON body. Crude and deliberate: the alternative is a
        mentions join table, and a mention is read once and never queried by
        anything else — so the join table would exist purely to make this one
        LIKE prettier. Substring collision is prevented by quoting: the body
        stores `"agent:ana/api-1"` with its quotes, so `dev:an` cannot match
        `dev:ana`.
        """
        rows = self.db.execute(
            'SELECT e.* FROM events e WHERE e.kind IN ("message", "handoff") '
            "AND e.body LIKE ? AND NOT EXISTS ("
            "  SELECT 1 FROM delivered d WHERE d.actor = ? AND d.event = e.id) "
            "ORDER BY e.ts, e.seq LIMIT ?",
            (f'%"{actor}"%', actor, limit)).fetchall()
        return [to_event(row) for row in rows]

    def mark(self, actor: str, ids: list[str], *, when: float) -> None:
        """Record delivery. Idempotent, so re-running a hook costs nothing."""
        self.db.executemany(
            "INSERT OR IGNORE INTO delivered (actor, event, ts) VALUES (?, ?, ?)",
            [(actor, event_id, when) for event_id in ids])
