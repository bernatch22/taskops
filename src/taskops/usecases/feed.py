"""Following the event log as it grows — what a live board (or a terminal) tails.

This is a use case rather than something the HTTP layer does itself, and the architecture test
is what said so: the feed needs a bus subscription and a cursor read, both of which are engine
and storage. Putting it here means the transport frames SSE and nothing else, and it means the
same feed can be tailed from the CLI without a second implementation.

**Why it polls a cursor rather than only listening to the bus.** Every writer is a different
process — MCP is stdio, so each editor session launches its own server, and each git hook is a
fresh interpreter. An in-process bus cannot see any of them. So the source of truth is
`events.after_seq(cursor)`, an indexed integer scan, and the bus subscription is layered on top
purely so the studio's OWN writes (a human's comment) appear instantly rather than on the next
tick. Both paths end at the same cursor read, so an event can never be delivered twice.
"""

from __future__ import annotations

import queue
from pathlib import Path
from typing import Iterator

from ..contracts import Event
from ..engine import BUS
from ..storage import Store, resolve_root

__all__ = ["follow", "TICK"]

TICK = 0.5
"""Seconds between cursor polls. Under the threshold where a board feels polled rather than
live, and two queries a second against an indexed integer column is nothing."""

_SIGNAL_DEPTH = 256


def follow(start: Path | str, after: int = -1, *,
           tick: float = TICK) -> Iterator[Event | None]:
    """Yield every event as it lands, and `None` on each quiet tick.

    The `None` is not a placeholder — it is how a consumer gets control back on a schedule
    without this module knowing what it wants to do with it. The studio emits an SSE keepalive;
    a terminal tailer redraws a clock; a test stops. Without it, a silent hour would be an hour
    with no way to notice the connection died.

    `after < 0` means "from now": a board that opened is asking what happens NEXT, and replaying
    the entire history into it would be a spike of thousands of frames it has no use for.
    """
    root = resolve_root(start)
    signal: queue.Queue[Event] = queue.Queue(maxsize=_SIGNAL_DEPTH)
    cancel = BUS.subscribe(lambda event: _offer(signal, event))
    store = Store(root, check_same_thread=False)
    try:
        cursor = store.events.max_seq() if after < 0 else after
        while True:
            _wait(signal, tick)
            fresh = store.events.after_seq(cursor)
            for event in fresh:
                yield event
            if fresh:
                cursor = store.events.max_seq()
            else:
                yield None
    finally:
        # Both, always. A browser tab that closes leaves this generator un-advanced, and without
        # the release every closed tab would strand a subscriber holding a sqlite connection —
        # which on a board somebody leaves open all day IS the failure mode.
        cancel()
        store.close()


def _wait(signal: "queue.Queue[Event]", tick: float) -> None:
    """Block up to one tick for an in-process write, then drop whatever piled up.

    The queued events are DISCARDED on purpose: they are a wake-up signal, and the cursor read
    that follows is what decides what to send. Treating the queue as the payload would give one
    event two delivery paths and a duplicate whenever both fired.
    """
    try:
        signal.get(timeout=tick)
    except queue.Empty:
        return
    while not signal.empty():
        signal.get_nowait()


def _offer(signal: "queue.Queue[Event]", event: Event) -> None:
    """Never block a WRITER. A full queue means a consumer is behind, and the cursor poll will
    catch it up anyway — so dropping the signal costs half a second, where blocking here would
    stall the use case that just recorded the event."""
    try:
        signal.put_nowait(event)
    except queue.Full:
        return
