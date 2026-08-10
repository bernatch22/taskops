"""holding — "is this history held HERE?", answered by event ids and nothing else.

One question, two callers, so the two cannot drift about what *safe* means:
`board pull` asks it after streaming the host's log down and BEFORE it flips
this checkout's config, and `board rm` asks it before a host destroys a board.
Same shape as `core/reports.py::under`, which guards the write and the read
from one place for the same reason.

**By ID, never by a count.** `cli/push.py` carries the post-mortem in its own
docstring: it compares totals and totals per kind, and a total that agrees says
NOTHING about WHICH events arrived — two logs of 402 events can share none of
them. So this takes SETS OF IDS. An event id is `sha256` of the event's own
canonical bytes (`core/event.py`), which makes "did this exact event arrive"
answerable by set membership and makes a re-run a no-op instead of a duplicate.

**Direction: theirs ⊆ mine.** Complete means the local copy holds every id the
host reported. Ids held HERE that the host never reported are not a fault and
are not counted: a local board may have moved on, and the question both callers
ask is "would anything be LOST", never "are these two identical". Say that out
loud in a refusal rather than reporting a symmetric difference nobody can act on.

**Never a bare boolean.** A refusal that says "incomplete" and stops sends
somebody to read code. `compare()` returns how many ids are missing plus a few
of them by name, ordered, so the sentence a caller writes can be checked against
the log by hand. `phrase()` renders exactly that gap for a human; the REFUSAL
around it — which commands make it possible, what will be destroyed — belongs to
the caller, the way `under()` leaves its wording to `verbs/record.py`.

**An empty host history is complete**, not an error: there is nothing there to
lose. The caller that finds this surprising is the one with a bug — say so with
`theirs`, which is on the answer for that reason.

Pure (layer 1): ids in, judgement out. No path, no store, no clock and no
network — the callers do the I/O, this does the deciding.
"""

from __future__ import annotations

from typing import Iterable, TypedDict

EXAMPLES = 3
"""How many missing ids travel with the answer. Enough to grep the log with,
few enough that a refusal stays one sentence."""


class Holding(TypedDict):
    """What the local copy holds of a host's history. Computed, never stored.

    `missing` is the number that decides `complete`, and `theirs`/`mine` are
    beside it because a refusal reading "3 events are missing" is a different
    conversation from "3 of 4" — and because two DISTINCT counts that agree
    while `missing` is non-zero is the exact failure `cli/push.py` was blind to.
    """

    complete: bool  # every id the host reported is held here
    theirs: int  # distinct ids the host reported
    mine: int  # distinct ids the local copy holds
    missing: int  # theirs, minus what is held here — 0 iff complete
    examples: list[str]  # up to EXAMPLES of the missing ids, sorted


def compare(theirs: Iterable[str], mine: Iterable[str]) -> Holding:
    """The judgement: is every event id in `theirs` held in `mine`?

    Both sides are read as SETS, so a log line that arrived twice cannot inflate
    a total — a duplicate is the same event by definition of the id. Blank ids
    are dropped from both sides: the empty string is not a `sha256` and is what
    a truncated wire row degrades into, so counting one would make a correct
    board look incomplete forever.

    `examples` is `sorted()` rather than iteration order: a set has none, and a
    refusal that names different ids on every run cannot be compared with the
    previous one.
    """
    host = {ident.strip() for ident in theirs} - {""}
    local = {ident.strip() for ident in mine} - {""}
    absent = sorted(host - local)
    return Holding(
        complete=not absent,
        theirs=len(host),
        mine=len(local),
        missing=len(absent),
        examples=absent[:EXAMPLES],
    )


def phrase(holding: Holding) -> str:
    """The gap, in words, for a caller assembling a refusal around it.

    Shared so `board pull` and `board rm` describe the same gap the same way;
    what to DO about it differs per caller and is deliberately not here.
    """
    if holding["complete"]:
        return f"all {holding['theirs']} event(s) are held here"
    shown = ", ".join(holding["examples"])
    more = "" if holding["missing"] <= len(holding["examples"]) else ", …"
    return (
        f"{holding['missing']} of the host's {holding['theirs']} event(s) are not here "
        f"(this copy holds {holding['mine']}) — e.g. {shown}{more}"
    )
