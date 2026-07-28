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

**And why it also carries things that are NOT events.** A narration delta is not a fact worth
storing — see `contracts.wire` — so it never reaches the database and there is no cursor that
could produce it. It rides the same generator because a browser has ONE socket: the alternative
is a second stream, a second subscription and a second lifetime to leak. A wire message is
yielded straight through, and the consequence is documented rather than hidden: it CANNOT be
recovered. A browser that reconnects missed whatever passed while it was away, and that is fine,
because the file on disk is the durable copy and the socket is only the window onto it.
"""

from __future__ import annotations

import queue
from pathlib import Path
from typing import Iterator

from ..contracts import Event, WireMessage
from ..engine import BUS, WIRE, is_wire
from ..storage import Store, resolve_root

__all__ = ["follow", "TICK", "is_wire"]

TICK = 0.5
"""Seconds between cursor polls. Under the threshold where a board feels polled rather than
live, and two queries a second against an indexed integer column is nothing."""

_SIGNAL_DEPTH = 256


def follow(start: Path | str, after: int = -1, *,
           tick: float = TICK) -> Iterator[Event | WireMessage | None]:
    """Yield every event as it lands, every wire message as it is published, and `None` on
    each quiet tick.

    The `None` is not a placeholder — it is how a consumer gets control back on a schedule
    without this module knowing what it wants to do with it. The studio emits an SSE keepalive;
    a terminal tailer redraws a clock; a test stops. Without it, a silent hour would be an hour
    with no way to notice the connection died.

    `after < 0` means "from now": a board that opened is asking what happens NEXT, and replaying
    the entire history into it would be a spike of thousands of frames it has no use for.
    """
    root = resolve_root(start)
    signal: "queue.Queue[WireMessage | None]" = queue.Queue(maxsize=_SIGNAL_DEPTH)
    # An event enqueues `None` — the SIGNAL to read the cursor, because the row is the payload.
    # A wire message enqueues ITSELF, because there is no row and never will be.
    cancels = (BUS.subscribe(lambda _event: _offer(signal, None)),
               WIRE.subscribe(lambda message: _offer(signal, message)))
    store = Store(root, check_same_thread=False)
    try:
        cursor = store.events.max_seq() if after < 0 else after
        while True:
            messages = _drain(signal, tick)
            yield from messages
            fresh = store.events.after_seq(cursor)
            yield from fresh
            if fresh:
                cursor = store.events.max_seq()
            elif not messages:
                # Only when NOTHING was delivered. A narration streaming at fifty deltas a second
                # would otherwise emit fifty keepalive ticks a second and burn the stream's
                # lifetime (`live.MAX_TICKS`) in the middle of the thing somebody is watching.
                yield None
    finally:
        # All of them, always. A browser tab that closes leaves this generator un-advanced, and
        # without the release every closed tab would strand a subscriber holding a sqlite
        # connection — which on a board somebody leaves open all day IS the failure mode.
        for cancel in cancels:
            cancel()
        store.close()


def _drain(signal: "queue.Queue[WireMessage | None]", tick: float) -> list[WireMessage]:
    """Block up to one tick, then take everything that piled up. Returns the wire messages.

    The `None`s are DISCARDED on purpose: they are a wake-up signal, and the cursor read that
    follows is what decides which events to send. Treating them as the payload would give one
    event two delivery paths and a duplicate whenever both fired. Wire messages are the opposite
    — they ARE the payload, since nothing else in this process knows they happened.
    """
    out: list[WireMessage] = []
    try:
        first = signal.get(timeout=tick)
    except queue.Empty:
        return out
    if first is not None:
        out.append(first)
    while not signal.empty():
        item = signal.get_nowait()
        if item is not None:
            out.append(item)
    return out


def _offer(signal: "queue.Queue[WireMessage | None]", item: WireMessage | None) -> None:
    """Never block a WRITER. A full queue means a consumer is behind, and the cursor poll will
    catch it up anyway — so dropping the signal costs half a second, where blocking here would
    stall the use case that just recorded the event.

    A dropped WIRE message is a lost fragment of prose and nothing more: the file on disk is
    being written in parallel, so the reader loses a moment of the animation, never the text."""
    try:
        signal.put_nowait(item)
    except queue.Full:
        return
