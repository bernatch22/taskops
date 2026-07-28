"""Events over HTTP: the half of remote sync that a server performs.

The git path (`storage.sync`) and this one move the SAME facts and rely on the same property —
ids are content hashes, so importing an event twice is a primary-key no-op. Nothing here
resolves a conflict because there is none to resolve: events are facts about the past, and the
union of two logs is the correct log.

**Seq is local, and that is the whole cursor design.** A puller's `after` is a number in the
SERVER's sequence, so a client keeps one cursor PER remote and may never mix two. Nothing on
the wire carries a seq inside an event for exactly that reason (`EventTable.page_after`).

**Local-only kinds are filtered in BOTH directions.** Outbound because `activity` is a
per-tool-call heartbeat and replicating it would add thousands of rows a day for nothing;
inbound because a server does not trust a client to have remembered the rule.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .._errors import BadRequest
from .._types import LOCAL_ONLY_KINDS
from ..contracts import Event
from ..engine import relay
from ..storage import event_from
from ._project import project

__all__ = ["accept_events", "pull_events", "MAX_BATCH", "MAX_PAGE"]

MAX_BATCH = 500
"""Events per POST. A cap and not a stream: the body is read into memory before anything looks
at it, so the limit has to bind before the allocation does. A client with more sends again."""

MAX_PAGE = 500


def accept_events(start: Path | str, raw: list[Any]) -> dict[str, int]:
    """Relay a foreign batch. Returns how many were NEW here, and this server's cursor.

    `accepted` is the idempotency signal the client logs: pushing the same batch twice answers
    0 the second time, which is how a person reading the output can tell a retry from a
    duplicate import.

    The whole batch is coerced BEFORE anything is written, so a malformed event at index 40
    cannot leave 39 relayed and the caller unsure how far it got.
    """
    if len(raw) > MAX_BATCH:
        raise BadRequest(f"{len(raw)} events in one push — send at most {MAX_BATCH} per "
                         f"request and repeat until the cursor stops moving")
    events = [_coerce(item, index) for index, item in enumerate(raw)]
    with project(start) as store:
        accepted = sum(1 for event in events if event is not None and relay(store, event))
        return {"accepted": accepted, "max_seq": store.events.max_seq()}


def pull_events(start: Path | str, *, after: int = 0, limit: int = MAX_PAGE) -> dict[str, Any]:
    """One page of this server's log after a cursor, plus where the cursor now stands.

    `more` reports that the PAGE was full, not that events are certainly waiting — the cheap
    answer, and the client's loop stops one request later either way.
    """
    size = max(1, min(limit, MAX_PAGE))
    with project(start) as store:
        page, cursor = store.events.page_after(after, limit=size)
        shared = [e for e in page if e["kind"] not in LOCAL_ONLY_KINDS]
        return {"events": shared, "max_seq": cursor, "more": len(page) == size}


def _coerce(item: Any, index: int) -> Event | None:
    """A wire object -> an event to relay, or None for one to drop. Raises on nonsense.

    The id is NOT recomputed — see `engine.log.relay` for why rebuilding it forks history.
    """
    event = event_from(item)
    if event is None:
        raise BadRequest(f"events[{index}] is not an event — it needs at least `id` and `kind`")
    return None if event["kind"] in LOCAL_ONLY_KINDS else event
