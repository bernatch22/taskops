"""Reading one plan entry — the fields, as a model actually writes them.

Split from `plan` by what the reader has to know: that module builds a graph, this one
decides what a caller meant when it packaged a field the way the schema did not name.
Every tolerance here is a habit observed in the field, not a defensive reflex — and each
one is the difference between rejecting a correct plan over a bracket and accepting it.

Nothing here guesses at a MEANING. A title is required and stays required; what gets
tolerated is only shape: a string where a list was declared, one value where a list of
one was.
"""

from __future__ import annotations

from typing import Any, cast

__all__ = ["title_of", "priority_of", "optional", "strings", "references", "blocked_ids"]

DEFAULT_PRIORITY = 2
"""The middle of the 0-3 band. A caller with no opinion about urgency has not said
"urgent", and defaulting to 0 would make every unconsidered task jump the queue."""


def title_of(entry: dict[str, Any]) -> str:
    return str(entry.get("title", "")).strip()


def priority_of(entry: dict[str, Any]) -> int:
    """`bool` is excluded explicitly: `True == 1` in Python, so a caller that sent
    `priority: true` would silently get an urgent task."""
    found = entry.get("priority")
    if isinstance(found, bool) or not isinstance(found, int):
        return DEFAULT_PRIORITY
    return found


def optional(entry: dict[str, Any], key: str) -> str | None:
    found = entry.get(key)
    return str(found) if isinstance(found, str) and found.strip() else None


def strings(entry: dict[str, Any], key: str) -> list[str]:
    """A list field, tolerating the comma-separated string a model reaches for anyway."""
    found: object = entry.get(key)
    if isinstance(found, str):
        return [part.strip() for part in found.split(",") if part.strip()]
    if isinstance(found, list):
        items = cast("list[object]", found)
        return [str(item).strip() for item in items if str(item).strip()]
    return []


def blocked_ids(entry: dict[str, Any]) -> list[str]:
    """`blocks` — the EXISTING tasks this new card must finish before.

    The inverse of `after`, and it exists for one flow: an agent mid-task discovers a prerequisite
    and needs "create this card AND make my current task wait for it" to be ONE call. Two calls meant
    two chances to do only the first, and the missing half is always the edge — leaving a card nobody
    is waiting for and a task that looks ready and is not.

    Ids only, never indexes: a card cannot block one created after it in the same batch without a
    cycle, so accepting an index here would only ever be a mistake worth rejecting.
    """
    found: object = entry.get("blocks")
    if isinstance(found, str):
        return [part.strip() for part in found.split(",") if part.strip()]
    if isinstance(found, list):
        items = cast("list[object]", found)
        return [str(item).strip() for item in items if str(item).strip()]
    return []


def references(entry: dict[str, Any]) -> list[object]:
    """The `after` field, however it was packaged.

    A bare value is wrapped: a model with one dependency writes `after: 0` about as
    often as `after: [0]`, and refusing the first rejects a correct plan over a bracket.
    Returned as `object` on purpose — an index and a task id are both legal, and
    telling them apart is `plan`'s decision, not this module's.
    """
    found: object = entry.get("after")
    if found is None or found == "":
        return []
    return list(cast("list[object]", found)) if isinstance(found, list) else [found]
