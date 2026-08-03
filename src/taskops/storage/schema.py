"""Bringing a database up to date. The tables themselves are in `_ddl`.

One database file per repository at `<repo>/.taskops/db.sqlite`, and it is a CACHE
— `storage.sync` can rebuild every row from the committed event log, which is why
it is gitignored and why a schema change needs no data-migration story.

**WAL, unlike megabrain.** That engine documents its rollback-journal choice as a
property of its workload rather than a preference: writes there are rare, so
readers already never wait. Here the workload is the opposite — a hundred agents
renewing leases and appending events continuously — and the studio reads this
database on every board refresh while they do. Under a rollback journal that
refresh stalls on each commit; WAL is what lets a reader run beside a writer.
"""

from __future__ import annotations

import sqlite3

from ._ddl import DDL

__all__ = ["apply"]

_PRAGMAS = ("PRAGMA journal_mode=WAL", "PRAGMA synchronous=NORMAL")
"""`synchronous=NORMAL` and not FULL: under WAL that risks losing the last commits
to an OS crash, never corruption — and the events those commits carry are also in
the log or re-derivable from git. Paying a full fsync per lease renewal to protect
data that is recoverable anyway is the wrong trade at a hundred agents.

`foreign_keys` is deliberately NOT set. There are no FK constraints in the schema:
`sync` imports events referring to tasks a `git pull` has not delivered yet, and a
constraint would reject exactly the events that make the project converge.
"""

_LATE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("tasks", "assignee TEXT NOT NULL DEFAULT ''"),
    ("tasks", "reviewer TEXT NOT NULL DEFAULT ''"),
    ("tasks", "milestone TEXT NOT NULL DEFAULT ''"),
    ("presence", "session TEXT NOT NULL DEFAULT ''"),
)
"""Columns added after a table shipped, applied with ALTER on every open so a database written by an
older taskops keeps working with no migration step anyone has to remember.

`assignee` is the mechanism's first user, and it worked exactly as intended: a database created
before dispatch existed gains the column on its next open, and every row defaults to the open pool —
which is what those rows meant."""

_LATE_INDEXES: tuple[str, ...] = (
    # A milestone's counts are read on every opening, statusline and board refresh, so the column
    # they group by is indexed. It cannot live in `DDL`: `executescript` runs BEFORE the ALTERs, so
    # on a database written by an older taskops the index would name a column that does not exist
    # yet — and one failing statement aborts the rest of the script, leaving the schema half
    # applied. An index over a late column is therefore itself late.
    "CREATE INDEX IF NOT EXISTS idx_tasks_milestone ON tasks(milestone)",
)


def apply(db: sqlite3.Connection) -> None:
    """Create everything missing and backfill late columns. Idempotent."""
    for pragma in _PRAGMAS:
        db.execute(pragma)
    db.executescript(DDL)
    for table, column in _LATE_COLUMNS:
        _add_column(db, table, column)
    for statement in _LATE_INDEXES:
        db.execute(statement)


def _add_column(db: sqlite3.Connection, table: str, column: str) -> None:
    """Add a late column, tolerating ONLY the already-present case.

    A bare `except OperationalError: pass` also swallows "database is locked",
    "disk I/O error" and "no such table" — every real reason a migration fails. The
    database then opens against a schema nobody migrated and fails later, somewhere
    else, with no trace of the migration that quietly gave up.
    """
    try:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column}")
    except sqlite3.OperationalError as err:
        if "duplicate column name" not in str(err).lower():
            raise
