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

    root: str
    """WHICH project emitted it: the absolute path of the store, as `str(store.root)`.

    A path and not a "project name" on purpose. The emitter is a narration running deep
    inside a use case; it does not know — and must not have to know — under which URL
    prefix some server happened to mount it, or whether it is mounted at all. The root is
    the one identifier both ends already share, and the consumer (`usecases.feed.follow`)
    resolves its own from the very same function.

    Never absent. The channel is process-global, so a server holding many boards open
    broadcasts every frame to all of them; a message that cannot say where it came from
    would be prose from one project appearing on another project's screen. That is why a
    message WITHOUT this field is dropped rather than delivered — see `follow`.

    It never reaches the browser: `transports.http.live` strips it before framing, because
    it is a path on the server's filesystem and no client has any business reading it.
    """
