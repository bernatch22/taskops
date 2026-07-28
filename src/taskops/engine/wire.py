"""The EPHEMERAL channel: things a watcher wants to see, that nobody should store.

Same shape as the event bus and deliberately a different object. `BUS` carries
`Event`s, and everything downstream of it — the cursor read, the export, the commit —
treats what it sees as a fact worth keeping. A narration delta is not that: it is
one of thousands of prose fragments per report, useful for the two minutes somebody
is watching the model write and worthless afterwards.

Publishing it here rather than there is what keeps `events.jsonl` readable as a diff.
The FILE is the durable copy; this is the window.

In-process only, like the bus, and for once that is not a limitation: the digest runs
inside the studio's own `ThreadingHTTPServer`, so the thread that publishes and the
thread parked in the live feed are the same process by construction.
"""

from __future__ import annotations

import threading
from typing import Callable, Generic, TypeVar

from ..contracts import WireMessage

__all__ = ["Broadcast", "WIRE", "is_wire"]

T = TypeVar("T")


class Broadcast(Generic[T]):
    """Publish/subscribe over a list, with a lock and no queue.

    Synchronous dispatch: a listener runs on the publisher's thread, which keeps a
    dropped message impossible for in-process subscribers and puts the cost of a slow
    listener where it can be seen. Every listener here does one thing — hand the item
    to its own outbound queue — which is the shape this requires.

    `subscribe` returns the way to UNDO itself rather than exposing a `remove`: a
    caller cannot hold a subscription it has no handle to, and a websocket that closes
    cannot forget which listener was its own.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._listeners: list[Callable[[T], None]] = []

    def subscribe(self, listener: Callable[[T], None]) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(listener)

        def cancel() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return cancel

    def publish(self, item: T) -> None:
        """Hand it to every listener. One that raises does not stop the rest.

        A subscriber is a UI connection, and a browser that vanished mid-write must not
        be able to abort the work that was publishing to it.
        """
        with self._lock:
            listeners = tuple(self._listeners)
        for listener in listeners:
            try:
                listener(item)
            except Exception:                    # noqa: BLE001 — a UI must not break a write
                continue

    def __len__(self) -> int:
        with self._lock:
            return len(self._listeners)


WIRE: Broadcast[WireMessage] = Broadcast()
"""The process-wide ephemeral channel. A module-level singleton for the same reason
`BUS` is: threading it through every use case to serve one optional subscriber, which
is always the same object — whatever is streaming to browsers."""


def is_wire(item: object) -> bool:
    """Whether a thing off the feed is an ephemeral frame rather than an `Event`.

    Structural, because both are plain dicts on the wire and the feed yields them down
    one channel. `label` and `text` together are what an `Event` never has — it carries
    `id`, `task` and `body` — so this cannot mistake one for the other.

    It lives in the engine rather than in `contracts`, where the types are, because
    layer 1 holds no logic at all; transports reach it through `usecases`.
    """
    return isinstance(item, dict) and "label" in item and "text" in item
