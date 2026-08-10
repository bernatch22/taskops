"""Reading a board's WHOLE log off a host, through the verb that already pages it.

Its own module, and the seam is a noun: `pull.py` is an ORDER — five steps, a
refusal at each, a config flip last — while this is a transport that knows
nothing about configs, checkouts or what the caller means to do with the log. It
exists because more than one command has to ask a host "what is your history",
and the answer must be assembled the same way each time or the two would
disagree about what "the whole log" means (`board pull` writes it down; `board
rm` compares it against what a checkout holds before anything is destroyed).

**No replication channel and no new server verb.** `events` is the paged read
the dashboard's Event pane already uses (`verbs/events.py`), and this is a
client of it with no more rights than any reader — which is what keeps this
inside the ban on git-style replication between clones (ARCHITECTURE §11).
Nothing is kept in step, and no cursor is stored anywhere between runs.

**Every line is verified on arrival.** An event whose id does not match its own
content is what `store/log.py` quarantines when reading a file; accepting one
over the wire and writing it down would put the corruption in a second place and
give it a fresh, trusted-looking home.
"""

from __future__ import annotations

from typing import Any

from ..core import event
from .._json import as_rows
from ..board import Board
from .._errors import TaskopsError
from ..core.types import Event
from ..verbs.events import MAX_PAGE

CORRUPT = (
    "{target} served an event whose id does not match its own content ({id}). Nothing was "
    "written here: an event that fails its own hash is what the log's reader quarantines, "
    "and storing it would put the corruption in a second place."
)


def whole_log(board: Board, target: str) -> tuple[list[Event], int]:
    """Every event the board holds, OLDEST FIRST, plus the length it claims.

    Keyset paging by `seq`, newest page first, exactly as the pane that already
    reads this verb does — an OFFSET shifts under a board somebody is still
    working on. `total` comes from the FIRST answer because that is the instant
    the read is a snapshot of: later pages only ever go older, so an event
    written mid-read is invisible to them and must not raise the number this
    read is measured against. A caller compares the two and refuses on a gap;
    that judgement is the caller's, because what to DO about it differs.

    Distinct by id, so a row served twice at a page boundary cannot inflate the
    count that is about to be compared against `total`.
    """
    found: dict[str, Event] = {}
    total, cursor = -1, 0
    while True:
        args: dict[str, Any] = {"limit": MAX_PAGE}
        if cursor:
            args["before"] = cursor
        answer = board.call("events", args)
        if total < 0:
            total = int(answer.get("total", 0) or 0)
        for row in as_rows(answer.get("events")):
            landed = event.of(row)
            if not event.verify(landed):
                raise TaskopsError(CORRUPT.format(target=target, id=landed["id"]))
            found.setdefault(landed["id"], landed)
        nxt = int(answer.get("next") or 0)
        # A cursor that does not go strictly backwards ends the read: paging a
        # server forever is a worse failure than a short read, which the
        # caller's own comparison against `total` catches anyway.
        if not nxt or (cursor and nxt >= cursor):
            return list(reversed(list(found.values()))), total
        cursor = nxt
