"""The in-process fan-out: a write here, a live board there.

Deliberately small, and deliberately NOT the delivery guarantee. Every taskops
process is short-lived and separate — MCP is a stdio transport, so each editor
session launches its own server, and each git hook is a fresh interpreter — so a
subscriber in one process cannot possibly see a publish in another.

That is why the studio does NOT rely on this. It polls `events.after_seq(cursor)`,
which is an indexed integer scan over a table every process writes to, and pushes
what it finds to browsers. This bus is the fast path for subscribers that live in
the SAME process as the writer — the studio's own writes, and the relay — so a
board updates without waiting for the next poll tick.

The honest summary: SQLite is the transport, and this is a latency optimisation. A
missed publish costs a fraction of a second, never a lost event.
"""

from __future__ import annotations

import threading
from typing import Callable

from ..contracts import Event

__all__ = ["EventBus", "BUS"]

Listener = Callable[[Event], None]


class EventBus:
    """Publish/subscribe over a list, with a lock and no queue.

    Synchronous dispatch: a listener runs on the publisher's thread. That keeps a
    dropped event impossible for in-process subscribers, and it puts the cost of a
    slow listener where it can be seen. The studio's listener does nothing but hand
    the event to its own outbound queue, which is the shape this requires.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._listeners: list[Listener] = []

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """Register, and hand back the way to undo it.

        Returning the unsubscribe rather than exposing a `remove` is what makes a
        leak hard: the caller cannot hold a subscription it has no handle to, and a
        websocket that closes cannot forget which listener was its own.
        """
        with self._lock:
            self._listeners.append(listener)

        def cancel() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return cancel

    def publish(self, event: Event) -> None:
        """Hand the event to every listener. One that raises does not stop the rest.

        A subscriber is a UI connection, and a browser that vanished mid-write must
        not roll back an event that is already committed to the database.
        """
        with self._lock:
            listeners = tuple(self._listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception:                    # noqa: BLE001 — a UI must not break a write
                continue

    def __len__(self) -> int:
        with self._lock:
            return len(self._listeners)


BUS = EventBus()
"""The process-wide bus. A module-level singleton because the alternative is
threading one through every use case to serve one optional subscriber — and the
subscriber is always the same object: whatever is streaming to browsers."""
