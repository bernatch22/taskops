"""Setting and reading a card's acceptance criteria, and judging the evidence for them.

Three jobs, one module, because they are one idea seen from three sides: what the card
promises, what a reader gets back, and whether a closing agent said anything that proves it.

The validation is deliberately LAX — it warns and never refuses. A criterion is worth having
even when its grammar is wrong, and the alternative to a warned line is not a better line, it
is no line at all. The engine guard downstream cares that criteria EXIST and that evidence
was given, never that either was well phrased.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from .._types import EventKind
from ..contracts.acceptance import ACCEPTANCE_KIND, KEYWORDS, SHALL, AcceptanceCheck
from ..engine import record
from ..storage import Store
from ._project import caller, heartbeat, project

__all__ = ["criteria_in", "check", "attach", "criteria_of", "set_acceptance", "acceptance_for"]

_KIND = cast("EventKind", ACCEPTANCE_KIND)
"""The cast names the one place this kind enters the log. A reader that does not know a kind
stores and forwards it untouched, which is how an older taskops carries these events."""


def criteria_in(raw: object) -> list[str]:
    """The criteria however the caller packaged them: a list, or one string of lines.

    Split on NEWLINES and never on commas, unlike every other list field here — an EARS line
    reads "WHEN the lease expires, THE SYSTEM SHALL requeue the card", and a comma split would
    turn one criterion into two halves that assert nothing.
    """
    if isinstance(raw, str):
        return [line.strip() for line in raw.splitlines() if line.strip()]
    if isinstance(raw, list):
        items = cast("list[object]", raw)
        return [str(item).strip() for item in items if str(item).strip()]
    return []


def check(criteria: list[str]) -> AcceptanceCheck:
    """The criteria, plus a warning for each line that does not read as EARS."""
    return AcceptanceCheck(criteria=criteria,
                           warnings=[_warning(line) for line in criteria if _off(line)])


def _off(line: str) -> bool:
    words = line.lower().split()
    return not words or words[0] not in KEYWORDS or SHALL not in words


def _warning(line: str) -> str:
    return (f'"{line[:60]}" does not read as EARS — the shape is '
            f'"WHEN <trigger> THE SYSTEM SHALL <response>". Kept as written')


def attach(store: Store, task_id: str, criteria: list[str], who: str) -> AcceptanceCheck:
    """Record the criteria for a card. Empty criteria record NOTHING.

    An event saying "this card has no criteria" is indistinguishable from a card nobody has
    set criteria on, and writing it would make every planned card carry a useless event.
    """
    result = check(criteria)
    if criteria:
        record(store, task=task_id, actor=who, kind=_KIND, body={"criteria": criteria})
    return result


def criteria_of(store: Store, task_id: str) -> list[str]:
    """What this card is accepted against — the LATEST statement, not the union.

    A rewrite replaces: criteria are what the card promises NOW, and merging an old list into a
    new one would resurrect a promise somebody deliberately dropped.
    """
    events = store.events.of_task(task_id, kinds=(ACCEPTANCE_KIND,))
    if not events:
        return []
    body: dict[str, Any] = events[-1]["body"]
    return criteria_in(body.get("criteria"))


def set_acceptance(start: Path | str, task_id: str, criteria: list[str], *,
                   actor: str = "") -> AcceptanceCheck:
    """The verb behind `tasks edit --acceptance` and the `acceptance` field of a plan entry."""
    with project(start) as store:
        who = caller(store, actor)["id"]
        heartbeat(store, who)
        store.tasks.need(task_id)
        return attach(store, task_id, criteria, who)


def acceptance_for(start: Path | str, task_id: str) -> AcceptanceCheck:
    """Read a card's criteria back, warnings and all — what a verifier opens first."""
    with project(start) as store:
        store.tasks.need(task_id)
        return check(criteria_of(store, task_id))
