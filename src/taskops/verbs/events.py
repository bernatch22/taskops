"""events — the log itself, newest first, one keyset page at a time.

The Monitor's Event stream is the one pane that reads the LOG rather than the
derived board: `pulse.py` answers "what is each card", this answers "what
happened, in order, ever". It was drawn to its full shape with `events={[]}`
for a whole chapter because no verb returned the rows.

Three decisions, all of them stated rather than assumed:

**Keyset, not offset, and by `seq`, not `ts`.** The cursor is a `seq` and the
reasoning lives where the SQL does (`store/cache.py::page`): the log grows
under the reader, so an offset shifts, and `ts` ties inside a single plan, so
a timestamp cursor drops or repeats the rows sharing the boundary instant.

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
    rows = stores.cache.page(before or None, limit)
    return {
        "events": [event for _, event in rows],
        # The cursor for the NEXT (older) page, or null when this one is the
        # tail. A short page cannot have more behind it; a full one might, and
        # the caller learns otherwise by asking and getting nothing back.
        "next": rows[-1][0] if len(rows) == limit else None,
        "total": stores.cache.count(),
        "head": stores.cache.head(),
    }
