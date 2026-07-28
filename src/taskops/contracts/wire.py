"""A message that travels on the SOCKET and is never stored.

The counterpart of `Event`, defined by what it is NOT: an event is the durable
record — hashed, written to sqlite, exported to `events.jsonl` and committed —
and a wire message is a frame the studio pushes to whoever happens to be looking.
Nothing persists it, nothing replays it, and a browser that reconnects has simply
missed it.

That distinction is load-bearing, not stylistic. The first thing this carries is
the narration of a report, arriving a few characters at a time; a thousand prose
fragments in `events.jsonl` would destroy the one property that file has, which is
that a human can read its diff. The FILE on disk is the durable copy of a
narration — this is only the window onto it being written.

`kind` is open for the same reason `Event.kind` is: a reader that does not know a
kind ignores the frame, and a newer taskops may send kinds this one never heard of.
"""

from __future__ import annotations

from typing import TypedDict

__all__ = ["WireMessage"]


class WireMessage(TypedDict):
    """One ephemeral frame: what happened, to which report, and the text of it."""

    kind: str
    """Namespaced by subject — `narration.delta`, `narration.pass`, `narration.done`,
    `narration.failed`. A consumer switches on it and drops what it does not know."""

    label: str
    """Which report this is about (`2026-07-28`, `2026-07-22..2026-07-28`, `all`).

    Never absent: two narrations can be in flight at once, and a delta that cannot
    say which document it belongs to would be appended to whichever panel is open.
    """

    text: str
    """The payload, shaped by `kind` — a fragment of prose for a delta, `2/4` for a
    pass, the failure verbatim for a failure, empty for a completion."""
