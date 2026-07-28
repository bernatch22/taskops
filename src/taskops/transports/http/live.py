"""The live feed: a WEBSOCKET for the browser, server-sent events as the fallback.

One route, two envelopes, one source. `usecases.follow` produces the events and the only difference
is the framing — so there is no second feed to keep in step.

**Why both.** The websocket is what a browser gets: its PING is the protocol's own liveness probe
(unlike an SSE comment, it gets an answer), and it is the channel that can carry a client→server
message the day the board needs one. SSE stays because it needs no handshake at all, which makes
`curl -N /api/live` a working debugging tool and gives a proxy that mangles upgrades a fallback.

**Why neither uses asyncio.** The engine is synchronous by an enforced invariant, so both are served
by the threaded `ThreadingHTTPServer`: one connection is one thread parked in a generator, and the
sqlite underneath never learns that a websocket exists. The RFC 6455 framing this needs is small
enough to write (`_wsframes`) and buys zero runtime dependencies — which matters in a package that
installs into every agent's environment on every machine.

The tailing itself is `usecases.feed`, because it needs the event bus and a cursor, and a transport
may not reach for either — including the filter that keeps one project's narration off another
project's board. This module only strips that routing field back off on the way out (`_public`).
"""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from typing import Any

from ...usecases import follow, is_wire
from . import websocket
from ._wire import Reply, Request

__all__ = ["stream"]

NARRATION = "narration"
"""The second thing this feed carries. An event is a stored fact and this is not — it is the prose
of a report arriving as a model writes it, published to `engine.WIRE`, never to the log. Same route and same socket on purpose: a browser holds one connection, and a second stream would
be a second subscription and a second lifetime to leak for what is one panel on one screen. The
envelope keeps them apart — a client that never heard of narration drops the frame."""

KEEPALIVE_TICKS = 4
"""Quiet ticks before a comment frame goes out — 4 × 0.5s = 2 seconds.

Proxies and browsers close an idle response, so something has to be sent. It is also how a write
eventually fails on a socket whose client went away — but only *eventually*, which is why it is not
the mechanism this relies on (see `MAX_TICKS`)."""

MAX_TICKS = 600
"""Ticks before the stream ends itself — 600 × 0.5s = 5 minutes. THE resource bound.

Measured, not assumed. The obvious design is a response that lives forever and ends when a write to
a departed client fails; that write does not reliably fail. Against a closed loopback socket on
macOS, writes kept succeeding for over seven seconds, so a closed tab held a bus subscription and an
open sqlite connection for an unbounded time — a real leak, found by the test below.

Ending the response on a schedule inverts the problem instead of fighting it: `EventSource`
reconnects on its own, by specification, and the UI refetches on every open — so a recycled stream
is invisible to the watcher, and resource use is bounded by DESIGN rather than by how promptly an
operating system reports a dead peer.
"""


def stream(root: Path, request: Request) -> Reply:
    """The live feed. A WEBSOCKET when the client asks to upgrade, SSE otherwise — one route
    serving both, for the reasons in this module's header.

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

    A quiet tick sends a PING, not a comment: the protocol's own liveness probe, and unlike the SSE
    keepalive it gets an answer, so the browser can tell a live-but-idle board from a dead socket.
    Both still end at `MAX_TICKS` — a parked generator cannot notice a departed client.
    """
    yield websocket.text_frame(json.dumps({"type": "hello"}))
    ticks = 0
    for event in follow(root):
        if is_wire(event):
            yield websocket.text_frame(json.dumps({"type": NARRATION, "message": _public(event)},
                                                  default=str))
            continue
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

    No resume cursor, deliberately. The `seq` a cursor would need is machine-local by design and is
    not part of the `Event` contract, so a frame has nothing honest to put in `id:` — and the
    recovery a board wants is not a replay anyway. The UI refetches the board and the fleet whenever
    the stream opens, which closes any gap in one request; events are only the signal to refetch.
    Replaying into a projection derived from the database is slower and less correct than reading it.
    """
    # Immediately, before the first tick. Two jobs: the UI's `onOpen` fires on it and refetches, and
    # a connection that was already dead on arrival raises here instead of parking for two seconds.
    yield b"event: hello\ndata: {}\n\n"
    quiet = 0
    ticks = 0
    for event in follow(root):
        if is_wire(event):
            quiet = 0
            yield _frame(_public(event), NARRATION)
            continue
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


def _public(message: Any) -> dict[str, Any]:
    """A wire message with its `root` STRIPPED — what a browser is allowed to see.

    The field routes the message inside the server (`usecases.follow`); on the wire it is only an
    absolute path on the server's filesystem, and on a multi-project server the name of a board
    this caller may hold no token for. A COPY, never a mutation: the broadcast handed the same
    dict to every subscriber and a message without a root is dropped, so popping the key in place
    would silence the board next door. Typed loosely — `is_wire` already ran at the call site.
    """
    return {key: value for key, value in message.items() if key != "root"}


def _frame(event: object, name: str = "change") -> bytes:
    """One SSE frame. The event NAME is what tells the two feeds apart — the websocket has no
    such line, which is why its envelope carries a `type` instead."""
    payload = json.dumps(event, default=str)
    return f"event: {name}\ndata: {payload}\n\n".encode("utf-8")
