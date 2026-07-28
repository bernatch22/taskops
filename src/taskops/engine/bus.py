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

The fan-out MACHINERY is `wire.Broadcast`, shared with the ephemeral channel that
carries narration deltas. Two singletons over one implementation, because the
difference between them is what they carry and who is allowed to persist it — not
how a listener is registered. A second hand-written publish/subscribe would drift.
"""

from __future__ import annotations

from typing import Callable, TypeAlias

from ..contracts import Event
from .wire import Broadcast

__all__ = ["EventBus", "BUS"]

Listener = Callable[[Event], None]

EventBus: TypeAlias = Broadcast[Event]
"""The bus's type, named. Kept as a name because it is the thing every caller and
every test refers to, and because "an EventBus" says what a `Broadcast[Event]` is
for."""

BUS: EventBus = Broadcast()
"""The process-wide bus. A module-level singleton because the alternative is
threading one through every use case to serve one optional subscriber — and the
subscriber is always the same object: whatever is streaming to browsers."""
