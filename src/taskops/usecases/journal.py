"""The server's log, kept true — because on a server, `db.sqlite` was the only copy.

Found by reading the box, not the code: four production boards, every one with a full database
and an `events.jsonl` of exactly 0 bytes. The architecture says the opposite in bold — the log
is truth, the database a disposable cache — and on every clone that holds. On the server it was
inverted, silently, because the two writers never exported: events recorded by the server's own
use cases sat with `exported=false` and nothing ever ran the exporter, while events relayed from
clones arrived marked `exported=true` and were skipped by design. One `rm db.sqlite` — the
documented repair for a cache — would have destroyed a board with no way back.

Making the server the single source of truth turned this from wrong into dangerous: the clones'
own logs used to be a de-facto distributed backup, and the single-source refactor retired them.
The one copy left was the disposable one.

Two verbs, two failure windows:

- `journal` runs after every mutating request — cheap (one indexed query, usually empty) and
  it bounds data loss to the events of a single in-flight request.
- `reconcile` runs when a server boots, and is the repair for every existing board: it walks
  the whole database against the whole file and appends what the file is missing, including
  everything that ever arrived through `relay` already marked exported.
"""

from __future__ import annotations

from pathlib import Path

from .._types import LOCAL_ONLY_KINDS
from ..storage import LOG_FILE, Store, export_events, read_log
from ..storage.sync import append_events

__all__ = ["journal", "reconcile"]


def journal(start: Path | str) -> int:
    """Append every unexported event to the log. Returns how many; safe after every request."""
    with Store(Path(start)) as store:
        return export_events(store)


def reconcile(start: Path | str) -> int:
    """Bring the log level with the database, whatever the flags claim. Returns the backfill.

    Reads the file's ids first and appends only what is missing, so it is idempotent and safe
    on a healthy board — where it costs one pass and writes nothing. The flag is ignored on
    purpose: `exported` means "the git path sent this", and on a server that path never ran,
    so trusting it is exactly how four boards ended up with empty logs.
    """
    root = Path(start)
    with Store(root) as store:
        known = {event["id"] for event in read_log(root)}
        missing = [event for event in store.events.all()
                   if event["id"] not in known and event["kind"] not in LOCAL_ONLY_KINDS]
        if missing:
            append_events(root / LOG_FILE, missing)
        store.events.mark_exported([event["id"] for event in missing])
        return len(missing)
