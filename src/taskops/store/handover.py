"""The hand-over — the one way a live work lease changes hands.

The lease is a mutex between PEERS. Two workers racing for the same card is
what it exists to settle, and there `INSERT OR IGNORE` decides it with no
prompt and no clock. The orchestrator is not a peer: it cut the worktree, it
named the worker, it spawned the process, and when that process dies it is the
only actor in the system that KNOWS. Making it wait out `LEASE_TTL` is making
it wait for a worse answer than the one it already holds.

Why the clock cannot be that answer, in either direction (2026-08-11, the
incident this module is the post-mortem for): the lease's only heartbeat is
`Live.renew`, called by every verb — so *MCP traffic* is the proxy for *alive*,
and the proxy is wrong both ways at once.

    a worker that DIED          keeps its card for up to 15 minutes,
                                and `assign` refuses the hand-over
    a worker that is WORKING    reads, edits and runs tests for 20 quiet
                                minutes without one MCP call, stops renewing,
                                and is reported `stalled` while it is alive

No value of `LEASE_TTL` fixes both — raising it worsens the first, lowering it
worsens the second. They are one bug pulling in opposite directions, and the
fix is to stop asking the clock a question it cannot answer.

This is NOT a `recover`, and re-reading `core/machine.py` before calling it one
is the point. `recover` was a verb any worker could aim at any card, that
resurrected a lease from a dead process and reported paths from a machine that
was not the caller's. This is none of that: no verb of its own (`assign` is the
only caller), no resurrection (the row is deleted, never revived), and the card
never returns to the pool — it goes to a NAMED replacement in the same call
that names it. The displaced worker is not punished either: a lapsed or
displaced lease still does not cost it the card it already built, because
`machine._not_somebody_elses` asks about the ASSIGNEE, not about the clock.
What changes hands is decided by somebody, on the record, in an event — never
by the passage of time.

A function over `Live.db` rather than a method, for the reason `reviews.py`
gives: `live.py` stays inside the 200-line budget along a seam.
"""

from __future__ import annotations

import sqlite3

from .live import Live
from .._errors import TaskopsError


def displace(live: Live, task: str, to: str, now: float) -> str | None:
    """Free `task`'s live lease so `to` can take it. Returns whoever held it, or
    None if nobody did — handing a card to the worker that already holds it is
    a no-op, not a displacement, so its lease is left exactly as it is."""
    holder = live.holder(task, now)
    if holder is None or holder == to:
        return None
    try:
        with live.db:
            live.db.execute("DELETE FROM leases WHERE task = ? AND actor = ?", (task, holder))
    except sqlite3.Error as err:
        raise TaskopsError(f"live store: cannot hand over {task}: {err}") from err
    return holder
