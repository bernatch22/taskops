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

    def beat(self, actor: str, dev: str, when: float, session: str = "") -> None:
        """Record a signal. The session is STICKY: an empty one never erases a known one.

        Every call heartbeats, and most of them carry no session — an MCP tool call, a git
        hook, a poll. If those overwrote the field, a developer would stop being reachable one
        second after their session opened, which is the opposite of what it records.
        """
        self.db.execute(
            "INSERT INTO presence (actor, dev, last_seen, session) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(actor) DO UPDATE SET last_seen = excluded.last_seen, "
            "dev = excluded.dev, "
            "session = CASE WHEN excluded.session != '' THEN excluded.session "
            "               ELSE presence.session END",
            (actor, dev, when, session))

    def devs(self, *, since: float, in_session: bool = False) -> dict[str, float]:
        """dev -> the freshest signal from ANY of that dev's actors, newest first.

        `in_session` narrows it to developers who have a SESSION open — somebody who can be
        given work. Without that distinction a board routed a review to the manager who had
        created its cards from a terminal four minutes earlier: present by every measure the
        store had, and never coming back. A dev counts as in-session when any of their actors
        carries a session id, which is how a session and the sub-agents it spawns stay one
        person: the agents call with no session of their own, and the dev row carries it.
        """
        rows = self.db.execute(
            "SELECT dev, MAX(last_seen) AS seen, MAX(session != '') AS live FROM presence "
            "WHERE last_seen >= ? AND dev != '' GROUP BY dev ORDER BY seen DESC",
            (since,)).fetchall()
        return {row["dev"]: row["seen"] for row in rows if row["live"] or not in_session}
