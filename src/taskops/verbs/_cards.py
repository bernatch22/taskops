"""Building one CARD out of a `tasks=[…]` row, and resolving the references in it.

Split out of `plan.py` at its own seam: that file owns the CALL (which chapter,
which events, what comes back), this one owns the row → `Card` coercion and the
one rule that makes a whole tree plannable in a single call — `parent`/`after`
may be an INDEX into the same call's `tasks`, because the ids do not exist yet
when the caller writes them.
"""

from __future__ import annotations

from . import _args
from .._errors import BadRequest
from ..core.types import Card, Milestone


def card(
    row: _args.Args, ident: str, stone: Milestone, actor: str, now: float, batch: list[str]
) -> Card:
    return Card(
        id=ident,
        title=_args.text(row, "title"),
        spec=_args.text(row, "spec", default=""),
        criteria=_args.strings(row, "criteria"),
        status="open",
        # Inherited from the chapter's `reviews` default; the card's own flag wins.
        review=_args.flag(row, "review", default=bool(stone.get("reviews", False))),
        priority=_args.number(row, "priority", default=2, low=0, high=3),
        milestone=stone["id"],
        parent=ref(row.get("parent"), batch),
        after=[r for r in (ref(x, batch) for x in listed(row.get("after"))) if r],
        files=_args.strings(row, "files"),
        labels=_args.strings(row, "labels"),
        assignee="",
        created_by=actor,
        created=now,
        updated=now,
    )


def listed(value: object) -> list[object]:
    if value is None or value == "":
        return []
    return list(value) if isinstance(value, list) else [value]  # type: ignore[arg-type]


def ref(value: object, batch: list[str]) -> str | None:
    """A reference is an index into this call's `tasks`, or a real card id."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise BadRequest("parent/after take an index or a card id, not a boolean")
    if isinstance(value, int):
        if not 0 <= value < len(batch):
            raise BadRequest(f"index {value} is outside this call's tasks (0..{len(batch) - 1})")
        return batch[value]
    if isinstance(value, str):
        return value
    raise BadRequest(f"parent/after take an index or a card id, got {type(value).__name__}")
