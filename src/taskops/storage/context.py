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
from ..contracts.context import CONTEXT_KIND, CONTEXT_TASK, SORTS, Fact, Sort
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


def matching(rows: list[Fact], prefix: str) -> list[str]:
    """Every fact id `prefix` could name, sorted — the whole id alone when it matches one.

    A PREFIX because `show` and `log` print eight characters, so the string a person can see is
    the only one they can retype. Ambiguity is returned rather than resolved: which of two the
    caller meant is not a question this layer may answer by picking.
    """
    if any(fact["id"] == prefix for fact in rows):
        return [prefix]
    return sorted(fact["id"] for fact in rows if fact["id"].startswith(prefix))


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
                actor=event["actor"], ts=event["ts"], retired=retired)


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
