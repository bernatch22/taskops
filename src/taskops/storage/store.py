"""The database: one SQLite file per repository, and the ONLY package with SQL.

`tests/architecture` enforces that. A query written anywhere else is a second place
that knows the column order, and it is always the one nobody updates when the
schema moves.

`Store` owns the connection and the schema; each table is its own object
(`store.tasks`, `store.leases`, …). Flat methods would make this file know every
table; this way it knows only the connection.
"""

from __future__ import annotations

import sqlite3
from functools import cached_property
from pathlib import Path
from types import TracebackType

from . import schema
from ._delivered import DeliveredTable
from ._deps import DepTable
from ._events import EventTable
from ._leases import LeaseTable
from ._tasks import TaskTable
from .locate import DB_FILE

__all__ = ["Store", "BUSY_TIMEOUT"]

BUSY_TIMEOUT = 15.0
"""Seconds a connection waits for a write lock before giving up.

Under WAL a reader never waits, so this bounds writer-versus-writer only. Fifteen
is generous against the writes taskops actually makes — a claim and an append, both
sub-millisecond — and it is deliberately SHORTER than a lease TTL: an agent that
cannot get the lock inside fifteen seconds should be told, not left hanging past
the point where its own claim expires underneath it.
"""


class Store:
    def __init__(self, root: Path, *, check_same_thread: bool = True) -> None:
        # check_same_thread=False lets the studio read from its request threads;
        # that server serialises its own writes, so it stays safe.
        self.root = Path(root)
        db_path = self.root / DB_FILE
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path, check_same_thread=check_same_thread,
                                  timeout=BUSY_TIMEOUT,
                                  isolation_level="DEFERRED")
        self.db.row_factory = sqlite3.Row
        schema.apply(self.db)

    # ---- tables (cached: one object per store, built on first touch)

    @cached_property
    def tasks(self) -> TaskTable:
        return TaskTable(self.db)

    @cached_property
    def deps(self) -> DepTable:
        """The DAG. Queried from both ends; see `_deps` for the direction."""
        return DepTable(self.db)

    @cached_property
    def leases(self) -> LeaseTable:
        """Claims with a deadline — the concurrency story. Writes go under
        `claiming()`, never bare, or the expiry sweep can interleave."""
        return LeaseTable(self.db)

    @cached_property
    def events(self) -> EventTable:
        return EventTable(self.db)

    @cached_property
    def delivered(self) -> DeliveredTable:
        return DeliveredTable(self.db)

    # ---- lifecycle

    def claiming(self) -> None:
        """Take the write lock NOW, before this call reads or writes anything.

        A claim is sweep-then-decide-then-insert, and under a DEFERRED transaction the lock
        is only taken at the insert — so two agents can both read the same dead lease as
        sweepable and both then try to claim. BEGIN IMMEDIATE closes that window.

        MUST be the first statement of the call. sqlite3 opens a transaction implicitly on
        the first write, and `BEGIN IMMEDIATE` inside one raises "cannot start a transaction
        within a transaction" — which is exactly how this was found, by an end-to-end test
        where a heartbeat wrote first. Tolerating that case with `if not in_transaction`
        would have been worse: the lock would silently not be taken, and the race this
        exists to prevent would be back with nothing to show for it.
        """
        self.db.execute("BEGIN IMMEDIATE")

    def commit(self) -> None:
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Clean exit commits; a raised exception rolls back. Always closes.

        sqlite3 opens a transaction on the first write and `close()` does NOT
        commit it, so a block that only closed would discard everything it wrote —
        a claim that reported success and left no lease.
        """
        try:
            self.db.rollback() if exc_type else self.db.commit()
        finally:
            self.close()
