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

__all__ = ["facts", "fact_of"]


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
    if sort not in SORTS:
        return None
    return Fact(id=event["id"], sort=_as_sort(sort), text=str(body.get("text", "")),
                labels=_strings(body.get("labels")), files=_strings(body.get("files")),
                horizon=str(body.get("horizon", "")), owner=str(body.get("owner", "")),
                actor=event["actor"], ts=event["ts"], retired=retired)


def _as_sort(value: str) -> Sort:
    return value                                # type: ignore[return-value]


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]        # type: ignore[misc]
