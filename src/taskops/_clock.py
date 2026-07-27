"""Layer 0 — the one place that asks what time it is.

Leases expire, heartbeats renew and events are ordered, so "now" is load-bearing
here rather than incidental. Routing it through one function is what lets a test
of "the agent died and its lease lapsed" run in microseconds instead of waiting
fifteen real minutes for the TTL.

`time.time()` and not `monotonic()`: these timestamps are compared ACROSS
machines and survive a restart, which a monotonic clock cannot do. The cost is
that a badly skewed clock skews a TTL — bounded, and visible in the studio,
where a lease from the future is obvious.
"""

from __future__ import annotations

import time

__all__ = ["now", "LEASE_TTL", "HEARTBEAT_GRACE"]

LEASE_TTL = 900.0
"""Seconds a claim survives without a heartbeat. Every taskops call an agent
makes renews it, so this bounds how long a task stays stuck after a CRASH —
not how long a legitimately slow task may run."""

HEARTBEAT_GRACE = 60.0
"""Extra seconds the studio waits before calling a session dead. A lease renews
on tool calls, and an agent that spends two minutes thinking has not gone away."""


def now() -> float:
    """Wall-clock seconds since the epoch."""
    return time.time()
