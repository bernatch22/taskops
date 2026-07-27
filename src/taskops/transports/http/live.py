"""The live feed: a WEBSOCKET for the browser, server-sent events as the fallback.

One route, two envelopes, one source. `usecases.follow` produces the events and the only difference
is the framing — so there is no second feed to keep in step.

**Why both.** The websocket is what a browser gets: it is what was asked for, its PING is the
protocol's own liveness probe (unlike an SSE comment, it gets an answer), and it is the channel that
can carry a client→server message the day the board needs one. SSE stays because it needs no
handshake at all, which makes `curl -N /api/live` a working debugging tool and gives a proxy that
mangles upgrades something to fall back to.

**Why neither uses asyncio.** The engine is synchronous by an enforced invariant, so both are served
by the threaded `ThreadingHTTPServer`: one connection is one thread parked in a generator, and the
sqlite underneath never learns that a websocket exists. The RFC 6455 framing this needs is small
enough to write (`_wsframes`) and buys zero runtime dependencies — which matters in a package that
installs into every agent's environment on every machine.

The tailing itself is `usecases.feed`, because it needs the event bus and a cursor, and a transport
may not reach for either.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path

from ...usecases import follow
from . import websocket
from ._wire import Reply, Request

__all__ = ["stream"]

KEEPALIVE_TICKS = 4
"""Quiet ticks before a comment frame goes out — 4 × 0.5s = 2 seconds.

Proxies and browsers close an idle response, so something has to be sent. It is also how a write
eventually fails on a socket whose client went away — but only *eventually*, which is why it is
not the mechanism this relies on (see `MAX_TICKS`)."""

MAX_TICKS = 600
"""Ticks before the stream ends itself — 600 × 0.5s = 5 minutes. THE resource bound.

Measured, not assumed. The obvious design is a response that lives forever and ends when a write
to a departed client fails; that write does not reliably fail. Against a closed loopback socket on
macOS, writes kept succeeding for more than seven seconds, so a closed tab held a bus subscription
and an open sqlite connection for an unbounded time — a real leak, found by the test below.

Ending the response on a schedule inverts the problem instead of fighting it: `EventSource`
reconnects on its own, by specification, and the UI refetches on every open — so a recycled stream
is invisible to the person watching, and resource use is bounded by DESIGN rather than by how
promptly an operating system reports a dead peer.
"""


def stream(root: Path, request: Request) -> Reply:
    """The live feed. A WEBSOCKET when the client asks to upgrade, SSE otherwise.

    One route serving both, because they are the same feed with two envelopes: `usecases.follow`
    produces the events and the only difference is the framing. The websocket is what the browser
    gets; SSE stays because it needs no handshake at all, which makes `curl -N /api/live` a working
    debugging tool and gives a proxy that mangles upgrades something to fall back to.

    `X-Accel-Buffering: no` is not decoration on the SSE path: nginx buffers a proxied response by
    default, and with it the whole feed arrives in one lump whenever the buffer happens to fill.
    """
    key = request.headers.get("sec-websocket-key", "")
    if websocket.is_upgrade(request.headers):
        return Reply(status=101, stream=lambda: _ws_frames(root),
                     headers=websocket.handshake_headers(key))
    return Reply(status=200, stream=lambda: _frames(root),
                 headers={"Content-Type": "text/event-stream; charset=utf-8",
                          "Cache-Control": "no-cache, no-transform",
                          "Connection": "keep-alive",
                          "X-Accel-Buffering": "no"})


def _ws_frames(root: Path) -> Generator[bytes, None, None]:
    """The same feed, in websocket frames.

    JSON with a `type` rather than SSE's `event:` line, because a websocket has no per-message event
    name — so the envelope carries it, and the browser switches on one field.

    A quiet tick sends a PING, not a comment: that is the protocol's own liveness probe, and unlike
    the SSE keepalive it gets an answer, so the browser can tell a live-but-idle board from a dead
    socket. Both still end at `MAX_TICKS` for the reason documented there — a parked generator cannot
    be relied on to notice a departed client.
    """
    yield websocket.text_frame(json.dumps({"type": "hello"}))
    ticks = 0
    for event in follow(root):
        if event is not None:
            yield websocket.text_frame(json.dumps({"type": "change", "event": event},
                                                  default=str))
            continue
        ticks += 1
        if ticks >= MAX_TICKS:
            yield websocket.close_frame()
            return
        if ticks % KEEPALIVE_TICKS == 0:
            yield websocket.ping_frame()


def _frames(root: Path) -> Generator[bytes, None, None]:
    """Turn the feed into SSE frames. Always from NOW, and no `id:`.

    No resume cursor, deliberately. The `seq` a cursor would need is machine-local by design and
    is not part of the `Event` contract, so a frame has nothing honest to put in `id:` — and the
    recovery a board actually wants is not a replay anyway. The UI refetches the board and the
    fleet whenever the stream opens, which closes any gap in one request; events are only the
    signal to refetch. Replaying a thousand events into a projection that is derived from the
    database would be slower and less correct than reading the database.
    """
    # Immediately, before the first tick. Two jobs: the UI's `onOpen` fires on it and refetches, and
    # a connection that was already dead on arrival raises here instead of parking for two seconds.
    yield b"event: hello\ndata: {}\n\n"
    quiet = 0
    ticks = 0
    for event in follow(root):
        if event is not None:
            quiet = 0
            yield _frame(event)
            continue
        ticks += 1
        quiet += 1
        if ticks >= MAX_TICKS:
            # Return, never raise. The generator's `finally` releases the store and the
            # subscription, the server closes the response, and the browser reconnects on its own.
            return
        if quiet >= KEEPALIVE_TICKS:
            quiet = 0
            yield b": keepalive\n\n"


def _frame(event: object) -> bytes:
    payload = json.dumps(event, default=str)
    return f"event: change\ndata: {payload}\n\n".encode("utf-8")
