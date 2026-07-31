"""Who has touched this store lately — the fact routing and the team brief are built on.

LOCAL state, like leases, and for the same reason: presence describes processes alive against
THIS store right now. Replicating it would tell another machine that somebody is "connected"
to a database they have never spoken to.

One row per actor, upserted on every heartbeat. The DEV is stored denormalised because every
reader asks "which developers are here" — a session and its agents are one person, and making
each read re-parse every actor id would put string parsing inside the routing decision.
"""

from __future__ import annotations

import sqlite3

__all__ = ["PresenceTable"]


class PresenceTable:
    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db

    def beat(self, actor: str, dev: str, when: float) -> None:
        self.db.execute(
            "INSERT INTO presence (actor, dev, last_seen) VALUES (?, ?, ?) "
            "ON CONFLICT(actor) DO UPDATE SET last_seen = excluded.last_seen, "
            "dev = excluded.dev",
            (actor, dev, when))

    def devs(self, *, since: float) -> dict[str, float]:
        """dev -> the freshest signal from ANY of that dev's actors, newest first."""
        rows = self.db.execute(
            "SELECT dev, MAX(last_seen) AS seen FROM presence "
            "WHERE last_seen >= ? AND dev != '' GROUP BY dev ORDER BY seen DESC",
            (since,)).fetchall()
        return {row["dev"]: row["seen"] for row in rows}
