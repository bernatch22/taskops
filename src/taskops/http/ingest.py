"""`board.ingest` — the door a LOCAL board's history walks through, once.

    {"verb": "board.ingest", "args": {"board": "facturador", "events": ["<line>", …]}}

This is what killed the scp. Promoting a local board used to be a sentence in
the README naming `events.jsonl` by its file name and a shell on the box: an
implementation detail turned into a manual step, with no count, no verification
and no way back. `cli/push.py` is the command; this is the half that receives.

**IT IS NOT A SYNC CHANNEL, AND IT CANNOT BECOME ONE.** The precondition below
is true exactly once in a board's life — the instant before it has any history
of its own — and everything about the verb depends on that. A board that has
observed one fact this call was not handed is refused, whatever the counts say,
because merging two histories means inventing an order between events that were
never in one timeline. There is no force flag and there must never be one: the
only honest answers are "this board was empty" and "no".

**It does not re-judge what it moves.** Every event here was validated by the
verb that made it (`core/event.py::make` refuses an unknown kind and a missing
body key), and its id is `sha256` of its own canonical bytes — so the door
verifies the HASH (a line that does not match its content never lands) and
nothing else. Re-running the verbs would be a second, divergent validator, and
the first event whose rules changed since it was written would be dropped.

**Retry is free, and that is why the whole history travels in ONE call.** The
ids are content-addressed, so re-sending an event is a no-op; what makes an
interrupted push resumable is the SET comparison — everything already on the
board must be one of the events in this call. That question is only decidable
when the whole history is in the call, so chunking it would buy nothing and
cost the only check that separates a retry from a stranger's board.

**Leases and presence do not travel.** `live.sqlite` is a live fact about
processes that are running, and none of them are running against this host. The
new board starts with nobody working on anything, which is true.
"""

from __future__ import annotations

from typing import Any
from collections import Counter

from .mounts import Mounts, named
from .._errors import Refused, NotFound, BadRequest
from ..core.event import verify, from_line
from ..core.types import PROJECT, Event
from ..store.stores import Stores

TWO_HISTORIES = (
    "board {name!r} on this host already holds {held} event(s) this push never "
    "observed — it is not empty, so there is nothing to promote INTO it. There is no "
    "force flag, deliberately: two histories would have to be given an order they "
    "never had, and taskops would be inventing a timeline instead of moving one. "
    "Push into a board created for it (`taskops board create <host>/<name>`), or "
    "keep working against the one that is already there."
)

NO_BOARD = (
    "no board named {name!r} on this host — a push moves a history INTO a board that "
    "already exists: make it first with `taskops board create <host>/{name}`"
)


def run(mounts: Mounts, args: dict[str, Any]) -> dict[str, Any]:
    """Move a whole history onto an empty board. Owner or member; gated by
    `core/scope.py::board.ingest` before this is ever reached."""
    name = named(str(args.get("board", "")).strip())
    incoming = _events(args)
    try:
        stores = mounts.stores(name)
    except NotFound as err:
        raise NotFound(NO_BOARD.format(name=name)) from err

    held = stores.ids()
    foreign = held - {event["id"] for event in incoming} - _birth(stores)
    if foreign:
        raise Refused(TWO_HISTORIES.format(name=name, held=len(foreign)))

    fresh = [event for event in incoming if event["id"] not in held]
    stores.write(fresh)
    landed = [event for event in incoming if event["id"] in stores.ids()]
    return {
        "board": name,
        "received": len(incoming),
        "written": len(fresh),
        # Non-zero on a RETRY and zero otherwise — the one number that says the
        # second run of an interrupted push did what it was supposed to: nothing.
        "already_held": len(incoming) - len(fresh),
        # READ BACK from the store, not counted from the payload: the whole point
        # of the comparison the client prints is that it is about what landed.
        "landed": len(landed),
        "kinds": Counter(event["kind"] for event in landed),
        "seq": stores.head(),
        "count": len(stores.ids()),
    }


def _birth(stores: Stores) -> set[str]:
    """A board's own birth certificate — and the reason "empty" is not `seq == 0`.

    `board.create` records WHO made the board as the board's FIRST event
    (`http/admin.py::_create`), because a creator is not derivable from a log
    that starts after the creation. So the board a push is aimed at — created
    minutes earlier by the same person, for this — already holds exactly one
    event, and a literal emptiness check refuses every correct push there is.
    The precondition is therefore "no history but its own beginning", and it is
    still true exactly once: after this call the board has a past.
    """
    return {
        event["id"]
        for event in stores.events(PROJECT)
        if event["kind"] == "project" and str(event["body"].get("op", "")) == "created"
    }


def _events(args: dict[str, Any]) -> list[Event]:
    """The log's OWN lines, decoded through the one coercion (`core/event.py`).

    Lines and not objects: what is being moved is `events.jsonl`, and a line is
    the exact unit its hash was taken over. Handing them across as JSON objects
    would put a second serialiser between the bytes that were hashed and the
    bytes that are checked, and the day the two disagree every event is corrupt.
    """
    raw = args.get("events")
    if not isinstance(raw, list) or not raw:
        raise BadRequest("board.ingest needs events=[<log line>, …] — a board push sends the log")
    lines: list[object] = list(raw)  # pyright: ignore[reportUnknownArgumentType]
    out: list[Event] = []
    for position, line in enumerate(lines, start=1):
        if not isinstance(line, str):
            raise BadRequest(f"event {position} of {len(lines)} is not a log line")
        event = from_line(line)
        if not verify(event):
            raise BadRequest(
                f"event {position} of {len(lines)} ({event['id']}) does not match its own "
                "content — nothing was written. That log line was altered after it was "
                "signed; `events.jsonl.quarantine` beside it is where such lines belong"
            )
        out.append(event)
    return out
