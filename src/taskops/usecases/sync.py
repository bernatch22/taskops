"""`taskops sync` — reconciling with what git brought in.

Import first, then export. That order is not arbitrary: importing can close a task whose
dependents this machine is about to be asked about, and exporting first would publish a
view of the graph that was already stale when it was written.

Called from `post-merge`, and safe to call at any time. Both directions are idempotent —
content-hash ids on the way in, an `exported` flag on the way out — so a developer who
runs it in a loop out of nervousness costs themselves nothing.
"""

from __future__ import annotations

from pathlib import Path

from ..engine import unblock
from ..storage import export_events, import_events
from ._project import project

__all__ = ["sync", "SyncReport"]


class SyncReport:
    """What moved, in both directions, plus what the import set free."""

    def __init__(self, *, imported: int, exported: int, unblocked: list[str]) -> None:
        self.imported = imported
        self.exported = exported
        self.unblocked = unblocked


def sync(start: Path | str) -> SyncReport:
    """Pull the log into the cache, push local events out, then re-derive readiness.

    `unblock` at the end is the point of the whole operation: a teammate finishing a
    task is only useful to this machine once the tasks waiting on it become pickable,
    and that promotion happens here rather than at the next `next` call — so a developer
    who runs `git pull` sees the real queue immediately.
    """
    with project(start) as store:
        imported = import_events(store)
        exported = export_events(store)
        return SyncReport(imported=imported, exported=exported,
                          unblocked=unblock(store))
