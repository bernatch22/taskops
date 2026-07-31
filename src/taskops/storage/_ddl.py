"""The tables, as SQL. Data, not logic — which is why it is not in `schema.py`.

That module is the part with bugs in it: pragmas, ALTERs, tolerating exactly one
kind of failure. This one is a declaration, and keeping them apart means a review
of a migration is not also a review of sixty lines of unchanged DDL.
"""

from __future__ import annotations

__all__ = ["DDL"]

DDL = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    spec TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 2,
    parent TEXT,
    labels TEXT NOT NULL DEFAULT '[]',      -- JSON array
    files TEXT NOT NULL DEFAULT '[]',       -- JSON array
    created_by TEXT NOT NULL,
    assignee TEXT NOT NULL DEFAULT '',
    reviewer TEXT NOT NULL DEFAULT '',      -- who may close it; "" is the stock verifier
    created REAL NOT NULL,
    updated REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee);

-- `task` must finish before `blocks` can start. Queried from BOTH ends, so both
-- directions are indexed: the primary key covers one, idx_deps_blocks the other.
CREATE TABLE IF NOT EXISTS deps (
    task TEXT NOT NULL,
    blocks TEXT NOT NULL,
    PRIMARY KEY (task, blocks)
);
CREATE INDEX IF NOT EXISTS idx_deps_blocks ON deps(blocks);

-- `task` is the PRIMARY KEY, and that is the entire locking story: two agents
-- racing to claim one task are two INSERTs on one key, and SQLite settles it.
CREATE TABLE IF NOT EXISTS leases (
    task TEXT PRIMARY KEY,
    actor TEXT NOT NULL,
    session TEXT NOT NULL DEFAULT '',
    branch TEXT NOT NULL DEFAULT '',
    acquired REAL NOT NULL,
    expires REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leases_actor ON leases(actor);

-- seq orders events on THIS machine; ts orders them across machines. Both are
-- needed: seq is what a live feed streams from, ts is what survives a sync.
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,                    -- the content, hashed: import twice = no-op
    seq INTEGER,
    task TEXT NOT NULL,
    actor TEXT NOT NULL,
    kind TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '{}',        -- JSON object, shaped by kind
    ts REAL NOT NULL,
    exported INTEGER NOT NULL DEFAULT 0     -- has the committed log seen this one
);
CREATE INDEX IF NOT EXISTS idx_events_task ON events(task, ts);
CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind, ts);
CREATE INDEX IF NOT EXISTS idx_events_export ON events(exported);

-- Delivery is per (actor, event), never a timestamp cursor: an agent's hooks fire
-- in an order nobody controls, and a cursor would skip whatever arrived late.
CREATE TABLE IF NOT EXISTS delivered (
    actor TEXT NOT NULL,
    event TEXT NOT NULL,
    ts REAL NOT NULL,
    PRIMARY KEY (actor, event)
);

-- Presence is LOCAL, like leases: it describes processes alive against THIS store.
CREATE TABLE IF NOT EXISTS presence (
    actor TEXT PRIMARY KEY,
    dev TEXT NOT NULL DEFAULT '',
    last_seen REAL NOT NULL,
    -- The session this actor was last seen inside, '' for a call that came from no session.
    -- It is what separates a developer who is HERE from one who ran a command and left: a
    -- board was once routed to a manager who had created the cards from a terminal minutes
    -- earlier, and the card waited on somebody who was never going to answer.
    session TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_presence_seen ON presence(last_seen);

CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""
