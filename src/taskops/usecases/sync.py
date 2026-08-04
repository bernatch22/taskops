"""`taskops sync` — reconciling with what git brought in.

Four steps, and the order is the design:

```
  import   the log's new events into the local cache        (storage)
  replay   those events into tasks and dependencies         (engine)
  unblock  re-derive what is now pickable                   (engine)
  export   this machine's new events into the log           (storage)
```

**Replay is the step that was missing**, and its absence was a real bug: following the usage guide,
a teammate's `git pull` imported every event and left them looking at an empty board. Events are the
source of truth, so something has to turn them into rows — see `engine.replay`.

Import before export, deliberately: importing can close a task whose dependents this machine is
about to be asked about, and exporting first would publish a view of the graph that was already
stale when it was written.

Every step is idempotent, so a developer who runs this in a loop out of nervousness costs themselves
nothing.
"""

from __future__ import annotations

from pathlib import Path

from ..engine import pickable, replay, unblock
from ..storage import all_events, export_events, import_events
from ._project import project
from .pushpull import pull
from .remote import read_remote, reset_cursor

__all__ = ["sync", "rebuild", "SyncReport"]


class SyncReport:
    """What moved, in both directions, plus what the import actually changed."""

    def __init__(self, *, imported: int, applied: int, exported: int,
                 unblocked: list[str]) -> None:
        self.imported = imported
        self.applied = applied
        """Events that changed local state. Lower than `imported` and that is normal — a comment is
        worth keeping and says nothing about what a task IS."""

        self.exported = exported
        self.unblocked = unblocked


def sync(start: Path | str) -> SyncReport:
    """Pull the log into the cache, apply it, re-derive readiness, push local events out.

    `unblock` at the end is the point of the whole operation: a teammate finishing a task is only
    useful here once the tasks waiting on it become pickable, and that promotion happens now rather
    than at the next `next` call — so somebody who just ran `git pull` sees the real queue.

    What it REPORTS as freed is a before/after diff of the pickable set, not `unblock`'s return.
    Since `unblock` records its moves, a promotion can arrive already made — replayed from the
    clone that derived it first — and reading only the local re-derivation then said "nothing
    became pickable" while handing the developer a pickable card. See `scheduler.pickable`.
    """
    if read_remote(start) is not None:
        # A remote project's truth is the SERVER, not a committed log — so "sync" means
        # refetch, from zero. The cursor reset is what makes a deleted `db.sqlite` a
        # non-event again: the cache rebuilds from the store that never lost anything.
        reset_cursor(start)
        got = pull(start)
        return SyncReport(imported=got.events_in, applied=got.applied,
                          exported=0, unblocked=got.unblocked)
    with project(start) as store:
        was_pickable = pickable(store)          # BEFORE the import, or the diff says nothing
        fresh = import_events(store)
        applied = replay.apply(store, fresh)
        unblock(store)
        return SyncReport(imported=len(fresh), applied=applied,
                          exported=export_events(store),
                          unblocked=sorted(pickable(store) - was_pickable))


def rebuild(start: Path | str) -> SyncReport:
    """Re-apply the ENTIRE log. The disaster-recovery path, for a deleted cache.

    Different from `sync` in one way that matters: it replays every event rather than only the new
    ones, because after `rm .taskops/db.sqlite` nothing is new — the log is all there is.

    Additive, never a truncate-and-replay: leases are live state the log does not describe, so
    wiping rows to rebuild them would drop every agent's claim to recreate what the log can
    reconcile anyway.
    """
    with project(start) as store:
        was_pickable = pickable(store)
        imported = len(import_events(store))
        applied = replay.apply(store, all_events(store.root))
        unblock(store)
        return SyncReport(imported=imported, applied=applied,
                          exported=export_events(store),
                          unblocked=sorted(pickable(store) - was_pickable))
