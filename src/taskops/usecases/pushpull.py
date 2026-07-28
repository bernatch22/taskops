"""`taskops push` and `taskops pull` — the same convergence as git, over HTTP.

The order is `usecases/sync.py`'s order and for the same reasons: events in, REPLAY, unblock,
and only then anything else. Replay is the step whose absence was a real bug — a teammate
imported every event and looked at an empty board, because events are the source of truth and
something has to turn them into rows. `pull` that only relayed would reproduce that bug over a
faster wire, so `tests/e2e/test_remote.py` asserts the imported card is on the BOARD, not that
its row is in the table.

**Push implies pull.** git does not do this and here it should: the round trip is one more
request against a server you just proved you can reach, and the alternative is two developers
whose boards have diverged since this morning, each convinced they are current.

**Marked exported only after a 200.** A push cut halfway through re-sends on the next run and
the server accepts each event exactly once — ids are content hashes — so the failure mode is
a duplicate request, not a lost event. The other order loses work to a dropped connection.

`push` keeps its OWN cursor (`pushed`, a local seq in remote.json) and never touches the
`exported` flag — that one belongs to the git-log export. The first version drained
`exported` instead, and on any project that had ever run `taskops sync` everything was
already marked: a 370-event board pushed as `0 event(s) out`, silently. Two sinks, two
cursors, and a project may use both — the jsonl for teammates on git, the server for the
live board.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from .._types import LOCAL_ONLY_KINDS
from ..contracts import Event
from ..engine import relay, replay, unblock
from ._project import locate, project
from ._reportsync import ReportSwap, exchange
from ._wireclient import PAGE, Wire
from .remote import require_remote, save_cursor, save_pushed

__all__ = ["push", "pull", "Exchange"]


class Exchange:
    """What crossed the wire, in both directions, plus what the import actually changed."""

    def __init__(self, *, events_in: int = 0, accepted: int = 0, applied: int = 0,
                 unblocked: list[str] | None = None) -> None:
        self.events_in = events_in
        self.accepted = accepted
        """Events the SERVER had never seen. Zero on a second push of the same work, which is
        the idempotency showing through rather than a failure."""

        self.applied = applied
        self.unblocked = unblocked or []
        self.reports = ReportSwap()


def pull(start: Path | str) -> Exchange:
    """Take the server's events, materialise them, and take any newer reports."""
    remote = require_remote(start)
    wire = Wire(remote["url"], remote["token"])
    done = _receive(start, wire, remote["cursor"])
    done.reports = exchange(wire, locate(start), upload=False)
    return done


def push(start: Path | str, *, force: bool = False) -> Exchange:
    """Send what is local, then pull, then reconcile reports in both directions."""
    remote = require_remote(start)
    wire = Wire(remote["url"], remote["token"])
    accepted = _send(start, wire, remote["pushed"])
    done = _receive(start, wire, remote["cursor"])
    done.accepted = accepted
    done.reports = exchange(wire, locate(start), upload=True, force=force)
    return done


def _send(start: Path | str, wire: Wire, pushed: int) -> int:
    """Page the LOCAL log past the push cursor. Returns how many were new on the server.

    The cursor advances only after the server's 200, so a push cut halfway re-sends and the
    content-hashed ids make the repeat a no-op. Local-only kinds are filtered out but their
    seqs still advance the cursor — skipping that would re-scan every activity heartbeat this
    machine ever wrote, which is most of the log.
    """
    accepted = 0
    while True:
        with project(start) as store:
            batch, tail = store.events.page_after(pushed, limit=PAGE)
            if not batch:
                return accepted
            shared = [e for e in batch if e["kind"] not in LOCAL_ONLY_KINDS]
        if shared:
            accepted += int(wire.post_events(cast("list[Any]", shared)).get("accepted", 0))
        save_pushed(start, tail)
        pushed = tail


def _receive(start: Path | str, wire: Wire, cursor: int) -> Exchange:
    """Page the server's log from the cursor, then REPLAY and unblock. Saves the cursor.

    The cursor is the server's `seq` and is never compared with a local one. A server that
    forgot it — a store rebuilt from scratch — answers from 0, and re-importing the whole log
    is a no-op rather than a repair job: `relay` accepts each content-hashed id once.
    """
    fresh: list[Event] = []
    with project(start) as store:
        while True:
            page = wire.get_events(cursor, PAGE)
            arrived = [cast("Event", row) for row in page.get("events", [])
                       if isinstance(row, dict)]
            fresh.extend(event for event in arrived if relay(store, event))
            cursor = max(cursor, int(page.get("max_seq", 0) or 0))
            if not page.get("more") or not arrived:
                break
        # Replay is not optional. Without it the events landed and the board stays empty.
        done = Exchange(events_in=len(fresh), applied=replay.apply(store, fresh),
                        unblocked=unblock(store))
    save_cursor(start, cursor)
    return done
