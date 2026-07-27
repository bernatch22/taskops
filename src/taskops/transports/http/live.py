"""The live feed as HTTP: server-sent events, one long response per browser.

**Why SSE and not WebSocket.** The plan called for a WebSocket; this is deliberately not one, and
every reason points the same way:

- The channel is **one-directional**. Everything the browser sends is an ordinary POST (a comment,
  a status change); everything the server sends is an event. WebSocket buys bidirectional binary
  framing, and taskops needs neither half of that.
- The engine is **sync**, and that is an enforced invariant. A WebSocket means asyncio or a
  hand-rolled framing layer inside a threaded handler — either one adds a whole concurrency model
  to a package whose storage story is "sqlite, synchronously".
- SSE is **stdlib**. Zero runtime dependencies is a product property here: taskops installs into
  every agent's environment on every machine, so a dependency here is a dependency everywhere.
- SSE **survives a proxy**. Behind two layers of nginx — which is where this ends up when a team
  wants the board on a wall — there is no upgrade to negotiate, and a browser reconnects on its
  own. That last property is load-bearing here, not incidental: see `MAX_TICKS`.

What is left in this file is framing. The tailing itself is `usecases.feed`, because it needs the
bus and a cursor and a transport may not reach for either.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path

from ...usecases import follow
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
    """An endless `text/event-stream`. The server flushes headers, then pulls the iterator.

    `X-Accel-Buffering: no` is not decoration: nginx buffers a proxied response by default, and
    with it the entire feed arrives in one lump whenever the buffer happens to fill.
    """
    return Reply(status=200, stream=lambda: _frames(root),
                 headers={"Content-Type": "text/event-stream; charset=utf-8",
                          "Cache-Control": "no-cache, no-transform",
                          "Connection": "keep-alive",
                          "X-Accel-Buffering": "no"})


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
