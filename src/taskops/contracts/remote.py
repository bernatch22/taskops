"""The ONE server this project syncs against, and this machine's place in its log.

One remote per project, deliberately. Two would be federation — the same event arriving
under two cursors, a report whose "who saw more" question has three answers — and none of
that is designed. `remote add` refuses the second one by name rather than silently keeping
a list nobody reads.

This is the only contract that carries a SECRET. It is written to `.taskops/remote.json`
with mode 0600, that path is inside the block `taskops init` gitignores, and no renderer
ever prints `token` — a token in a commit is the exact disaster the file mode exists to
prevent, and it survives every rotation of the branch it landed on.
"""

from __future__ import annotations

from typing import TypedDict

__all__ = ["Remote"]


class Remote(TypedDict):
    url: str
    """The server's base, with no trailing slash — `https://taskops.example.com`."""

    token: str
    """The bearer sent on every request. Never printed, never rendered, never committed."""

    cursor: int
    """The last `seq` this machine imported FROM THAT SERVER.

    A SERVER-side number, and it is only ever compared against server-side numbers: every
    sqlite numbers its own rows, so measuring this against a local `seq` would be a
    coincidence pretending to be an ordering.

    If the server forgets it — a store recreated from scratch — the next `GET /api/sync`
    answers from 0 and the client re-imports everything. That is a no-op, not a repair
    job: ids are content hashes, so `relay` accepts each event exactly once no matter how
    many times it is offered.
    """
