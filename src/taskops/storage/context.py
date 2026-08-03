"""The context projection: context events -> the facts in force.

Derived on every read rather than materialised into a table, deliberately. The log arrives
out of order (a `git pull` merges two ends of a file) and a retire can land before the fact
it retires, so a stored `retired` column would need a repair pass that a fold over the events
does not. There are tens of these facts, not thousands.

It lives in `storage/` because it is a read over the event table, and it goes through
`EventTable.of_task` rather than a new query: the sentinel task id already has an index, so
the whole context is one indexed scan and this module owns no SQL of its own.
"""

from __future__ import annotations

from ..contracts import Event
from ..contracts.context import CONTEXT_KIND, CONTEXT_TASK, LEVELS, SORTS, Fact, Level, Sort
from ._prefix import matching
from .store import Store

__all__ = ["facts", "fact_of", "matching"]


def facts(store: Store, *, retired: bool = False) -> list[Fact]:
    """Every context fact, oldest first. `retired=True` includes the withdrawn ones.

    Two views out of one fold because they are two questions: `show` asks what is in force,
    `log` asks what we have ever believed — and the second one is the entire reason retiring
    is an event instead of a DELETE.
    """
    events = store.events.of_task(CONTEXT_TASK, kinds=(CONTEXT_KIND,))
    gone = {str(e["body"].get("retires", "")) for e in events}
    found = [fact_of(e, retired=e["id"] in gone) for e in events]
    live = [f for f in found if f is not None]
    return sorted(live if retired else [f for f in live if not f["retired"]],
                  key=lambda f: (f["ts"], f["id"]))


def fact_of(event: Event, *, retired: bool = False) -> Fact | None:
    """One event -> the fact it states, or None when it states none.

    None covers both a retire event (which carries no `sort`) and a `sort` written by a newer
    taskops this version has never heard of. Skipping instead of raising is the same contract
    the log reader already keeps: one unknown line must not make the project unreadable.
    """
    body = event["body"]
    sort = str(body.get("sort", ""))
    scope: tuple[list[str], list[str]] = (_strings(body.get("labels")),
                                          _strings(body.get("files")))
    if sort in _RETIRED:
        # A fact written as an `invariant` by an older taskops. Read as a decision — the sort is
        # gone — and its SCOPE IS DROPPED, which is the whole care this mapping takes: an
        # invariant reached every card whatever its labels said, so a remapped one that kept
        # them would quietly stop reaching most of them. Preserving the meaning is preserving
        # "reaches everything", not preserving the field.
        sort, scope = _RETIRED[sort], ([], [])
    if sort not in SORTS:
        return None
    return Fact(id=event["id"], sort=_as_sort(sort), text=str(body.get("text", "")),
                labels=scope[0], files=scope[1],
                horizon=str(body.get("horizon", "")), owner=str(body.get("owner", "")),
                milestone=str(body.get("milestone", "")), level=_level_of(body),
                actor=event["actor"], ts=event["ts"], retired=retired)


def _level_of(body: dict[str, object]) -> Level:
    """A fact's lifetime, and the whole compatibility question in four lines.

    A body with NO `level` was written before levels existed, and it reads as `project` —
    permanently in force, attached to no chapter. Not `milestone`, which is the default a WRITER
    gets today: a legacy fact has no chapter to belong to, so calling it milestone-level would
    attach it to whichever one happens to be open now and then drop it from every slice the moment
    that chapter closed. A board's standing rules may not vanish because a version changed; same
    argument as `_RETIRED` below, one field over.

    An unrecognised level falls the same way, for the same reason: a value a NEWER taskops wrote
    is one this one cannot place, and the safe failure is "still in force" rather than "gone".
    """
    stated = str(body.get("level", ""))
    return stated if stated in LEVELS else "project"    # type: ignore[return-value]


_RETIRED = {"invariant": "decision"}
"""Sorts a previous taskops wrote and this one does not have. Mapped rather than dropped: the
reader skips an UNKNOWN sort, which is right for one a newer version invented and wrong for one
this version retired — that would make a board's standing rules vanish from every slice with no
error anywhere. Same shape as `engine.replay._RETIRED`, which does it for a status."""


def _as_sort(value: str) -> Sort:
    return value                                # type: ignore[return-value]


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]        # type: ignore[misc]
