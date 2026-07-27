"""Recording that something happened. The one door into the event log.

Every fact enters through `record`, which means three things happen together and
cannot drift apart: the row is written, the id is derived from the content, and the
live subscribers are told. A use case that wrote the table directly would be an
event nobody sees on the board and nobody can replicate.

Nothing here decides ANYTHING. `record` does not check a lease or a transition — by
the time it is called, `machine` has already allowed the move. That separation is
what lets the ingest path record a commit somebody made by hand outside any claim.
"""

from __future__ import annotations

from typing import Any

from .._clock import now
from .._ids import event_id
from .._types import EventKind
from ..contracts import Event
from ..storage import Store
from .bus import BUS

__all__ = ["record", "build"]


def build(*, task: str, actor: str, kind: EventKind, body: dict[str, Any] | None = None,
          ts: float | None = None) -> Event:
    """An event with its id derived from its content.

    Split from `record` so a caller can construct one without a database — which is
    what the relay does when it forwards, and what the tests do when they need an
    event whose id they can predict.
    """
    when = now() if ts is None else ts
    payload = body or {}
    return Event(id=event_id(task=task, actor=actor, kind=kind, body=payload, ts=when),
                 task=task, actor=actor, kind=kind, body=payload, ts=when)


def record(store: Store, *, task: str, actor: str, kind: EventKind,
           body: dict[str, Any] | None = None, ts: float | None = None) -> Event:
    """Write it, then announce it. Returns the event either way.

    The event is returned even when it was already present, because the caller's
    next step is usually to report what it recorded and a None here would make every
    call site handle a case that is not an error.
    """
    event = build(task=task, actor=actor, kind=kind, body=body, ts=ts)
    if store.events.append(event):
        BUS.publish(event)
    return event


def relay(store: Store, event: Event) -> bool:
    """Accept an event that came from elsewhere, verbatim. True if it was new.

    The id is NOT recomputed. A foreign event's id is its identity, and rebuilding
    it here would silently fork history the moment a newer taskops adds a body field
    this version does not serialize identically.

    That means a bad actor could forge an id, which is worth being explicit about:
    the trust boundary is the git remote and the relay's token, not this function.
    """
    accepted = store.events.append(event, exported=True)
    if accepted:
        BUS.publish(event)
    return accepted
