"""events — the log itself, one keyset page at a time, in whichever direction
the reader is going.

The Monitor's Event stream and the Editor's Stream rail are the two panes that
read the LOG rather than the derived board: `pulse.py` answers "what is each
card", this answers "what happened, in order, ever". It was drawn to its full
shape with `events={[]}` for a whole chapter because no verb returned the rows.

Four decisions, all of them stated rather than assumed:

**Keyset, not offset, and by `seq`, not `ts`.** The cursor is a `seq` and the
reasoning lives where the SQL does (`store/cache.py::page`): the log grows
under the reader, so an offset shifts, and `ts` ties inside a single plan, so
a timestamp cursor drops or repeats the rows sharing the boundary instant.

**Two directions, one verb, and `next` means the same thing in both** — the
cursor for the page you have NOT read yet, in the direction you are reading.
`before=` reads BACKWARDS into history, newest first, and `next` is the older
cursor. `after=` reads FORWARDS from a cursor the reader already holds: the
rows written since, OLDEST first, and `next` is where to carry on from when
the catch-up did not fit in one page. The two cannot be asked at once — that
is two questions — and the refusal says so.

**The cursor a live reader carries is `head`, not a `seq` per row.** Line 53
drops the rowid on the way out and that stays true: a reader takes the `head`
of the answer it read, and asks `after=<that head>` next time. It gets EXACTLY
the rows written in between — no arithmetic over a page, no dedupe by id, and
no way to be wrong when a burst is larger than a page (it pages forward on
`next` instead). The client-side derivation that came before it is written out
in `ui/src/components/toasts/model.ts`, which is the shape this replaces.

**No milestone filter.** A stored event carries no milestone — resolving one
would mean looking up every row's card on every page, and `task="project"`
rows (the board's own history: a repo bound, a chapter opened) belong to no
chapter at all, so a filtered stream would silently hide exactly the history
this pane exists to show. The stream is board-wide, always, and the pane says
so on its face. If a per-chapter stream is ever wanted it is a different
question with a different answer (the milestone's cards' threads), not an
argument bolted onto this one.

**`total` is the log's real length**, from `cache.count()` — the counter in
the pane's header is the number of events the board has, not the number this
page happened to return.
"""

from __future__ import annotations

from typing import Any

from . import _args
from .. import _clock
from .._errors import BadRequest
from ..store.stores import Stores

#: Rows per page. The pane scrolls inside a 620px box; this fills it twice.
PAGE = 50
MAX_PAGE = 200

#: A cursor is a rowid. The ceiling is JS's exact-integer limit, because the
#: caller that pages this log is a browser and a cursor it cannot represent is
#: a cursor it would send back wrong.
MAX_CURSOR = 2**53 - 1


def run(stores: Stores, actor: str, args: _args.Args) -> dict[str, Any]:
    stores.live.renew(actor, _clock.now())
    limit = _args.number(args, "limit", default=PAGE, low=1, high=MAX_PAGE)
    before = _args.number(args, "before", default=0, low=0, high=MAX_CURSOR)
    after = _args.number(args, "after", default=0, low=0, high=MAX_CURSOR)
    if before and after:
        raise BadRequest(
            "before= reads back into history and after= reads forward from a cursor;"
            " ask one of them — call events again for the other"
        )
    rows = (
        stores.cache.since(after, limit) if after else stores.cache.page(before or None, limit)
    )
    return {
        "events": [event for _, event in rows],
        # The cursor for the page NOT read yet, in the direction of travel: the
        # next OLDER row going back, the next NEWER row catching up. Null means
        # the reader is at that end of the log — the tail of history going back,
        # up to date coming forward. A short page cannot have more behind it; a
        # full one might, and the caller learns otherwise by asking and getting
        # nothing back.
        "next": rows[-1][0] if len(rows) == limit else None,
        "total": stores.cache.count(),
        "head": stores.cache.head(),
    }
