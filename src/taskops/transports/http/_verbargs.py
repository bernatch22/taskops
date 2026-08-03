"""The adapters `_verbs` needs — the rows that cannot be a one-line lambda.

Split out when the table hit its budget with a verb still to add, and the split says what each
half is: `_verbs` is the LIST, this is the handful of ARGUMENT shapes that do not fit on the
row. A verb lands here only because its arguments need reshaping or its result is a class that
has to be told how to cross the wire — never because it does logic, which belongs in a use case.

Keeping them apart is what lets the list stay a list: a table nobody can add a row to without
first deleting something is a table that stops describing the surface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ... import usecases as uc
from ...usecases.capture import assign

__all__ = ["strings", "span", "assigned", "recovered"]


def strings(args: dict[str, Any], key: str) -> list[str]:
    found = args.get(key)
    return [str(item) for item in found] if isinstance(found, list) else []


def span(args: dict[str, Any]) -> uc.Selector:
    return uc.Selector(date=str(args.get("date", "")), last=str(args.get("last", "")),
                       from_date=str(args.get("from_date", "")), to=str(args.get("to", "")),
                       whole=bool(args.get("whole")))


def assigned(root: Path, args: dict[str, Any]) -> dict[str, str]:
    return {"assigned": assign(root, str(args.get("task", "")), str(args.get("to", "")),
                               actor=str(args.get("actor", "")))}


def recovered(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    """`Recovered` and `Stuck` are classes, so this says how they cross the wire."""
    from ..._clock import HEARTBEAT_GRACE

    done = uc.recover(root, actor=str(args.get("actor", "")),
                      grace=float(args.get("grace", 0) or 0) or HEARTBEAT_GRACE,
                      force=bool(args.get("force")))
    return {"alive": done.alive,
            "released": [{"task": s.task, "actor": s.actor, "silent_for": s.silent_for,
                          "commits": s.commits, "leftovers": s.leftovers,
                          "tree": str(s.tree)} for s in done.released]}
