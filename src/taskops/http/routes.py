"""Where a request path splits into `(board, tail)` — ONE function, shared by
GET and POST so the two methods cannot disagree about what a path names. Split
out of `handler.py` at the seam that owns no HTTP at all (this module sees
strings, never sockets), because the handler sits on the ≤200-line budget
`tests/test_architecture.py` enforces.

`api/` is stripped HERE, once. Since the board's own address became the page
(tk-32d2ba), the machine doors — rpc, git, feed, invite/redeem — also answer
under `/<board>/api/…`, which is the spelling the page uses from now on.
Stripping in the split rather than per door means every door gets both
spellings and none can drift: `/<board>/api/rpc` IS `/<board>/rpc` — same
handler, same credential, same words. The 0.5.0 spellings stay, unprefixed,
because agents, the MCP client, `taskops ui`'s upstream forward and four
legacy production boards speak them today.

The prefix cannot shadow a page asset: the packaged bundle's filenames are a
CLOSED SET and none of them is named `api` (`static.asset` argues the same
fact from the router's other side). And the ROOT is untouched — `/login`,
`/rpc` and `/healthz` are one segment, so the strip, which lives in the TAIL,
never sees them; a board named `api` still answers at `/api/…` because the
strip runs after the board segment is taken.
"""

from __future__ import annotations


def split(path: str) -> tuple[str, str]:
    clean = path.partition("?")[0].strip("/")
    board, _, tail = clean.partition("/")
    if tail.startswith("api/"):
        tail = tail[4:]
    return board, tail
