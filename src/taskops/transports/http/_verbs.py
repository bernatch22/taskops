"""The rpc registry — the whitelist of verbs a clone may run in this store.

Split from `rpc` when the table outgrew the module budget, and the split says what each half
is: `rpc` is the DOOR (parse, refuse, guard), this is the LIST. A new remote-safe verb is one
row here; a verb that stays off this list stays local, which is the security posture.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ... import usecases as uc
from ...usecases.capture import assign
from ...usecases.ingest import bind
from ...usecases.pick import pick

__all__ = ["VERBS", "Verb"]

Verb = Callable[[Path, dict[str, Any]], Any]


def _strings(args: dict[str, Any], key: str) -> list[str]:
    found = args.get(key)
    return [str(item) for item in found] if isinstance(found, list) else []


def _span(args: dict[str, Any]) -> uc.Selector:
    return uc.Selector(date=str(args.get("date", "")), last=str(args.get("last", "")),
                    from_date=str(args.get("from_date", "")), to=str(args.get("to", "")),
                    whole=bool(args.get("whole")))


def _assigned(root: Path, args: dict[str, Any]) -> dict[str, str]:
    return {"assigned": assign(root, str(args.get("task", "")), str(args.get("to", "")),
                               actor=str(args.get("actor", "")))}


def _recovered(root: Path, args: dict[str, Any]) -> dict[str, Any]:
    """`Recovered` and `Stuck` are classes, so this row says how they cross the wire."""
    from ..._clock import HEARTBEAT_GRACE

    done = uc.recover(root, actor=str(args.get("actor", "")),
                   grace=float(args.get("grace", 0) or 0) or HEARTBEAT_GRACE,
                   force=bool(args.get("force")))
    return {"alive": done.alive,
            "released": [{"task": s.task, "actor": s.actor, "silent_for": s.silent_for,
                          "commits": s.commits, "leftovers": s.leftovers,
                          "tree": str(s.tree)} for s in done.released]}


VERBS: dict[str, Verb] = {

    # writes — the reason this endpoint exists
    "plan": lambda root, a: uc.plan(root, list(a.get("entries", [])), actor=str(a.get("actor", ""))),
    "edit": lambda root, a: uc.edit(root, str(a.get("task", "")), title=a.get("title"),
                                 spec=a.get("spec"), priority=a.get("priority"),
                                 reviewer=a.get("reviewer"), acceptance=a.get("acceptance"),
                                 actor=str(a.get("actor", ""))),
    "acceptance": lambda root, a: uc.set_acceptance(root, str(a.get("task", "")),
                                                 _strings(a, "criteria"),
                                                 actor=str(a.get("actor", ""))),
    "assign": lambda root, a: _assigned(root, a),
    "pick": lambda root, a: pick(root, tasks=tuple(_strings(a, "tasks")),
                                 count=int(a.get("count", 0) or 0),
                                 actor=str(a.get("actor", "")),
                                 dry_run=bool(a.get("dry_run"))),
    "recover": lambda root, a: _recovered(root, a),
    "bind": lambda root, a: bind(root, a),
    "context_state": lambda root, a: uc.context_state(root, str(a.get("sort", "")),
                                                   str(a.get("text", "")),
                                                   labels=_strings(a, "labels"),
                                                   actor=str(a.get("actor", ""))),
    "context_retire": lambda root, a: uc.context_retire(root, str(a.get("id", "")),
                                                     actor=str(a.get("actor", ""))),
    # reads — served from the one store every write above landed in
    "ask": lambda root, a: uc.ask(root, str(a.get("task", "")), actor=str(a.get("actor", ""))),
    "search": lambda root, a: uc.search(root, str(a.get("query", "")),
                                     limit=int(a.get("limit", 20) or 20)),
    "attention": lambda root, _a: uc.attention(root),
    "board": lambda root, _a: uc.board(root),
    "standup": lambda root, a: uc.standup(root, since=str(a.get("since", "")) or "24h",
                                       actor=str(a.get("actor", ""))),
    "day": lambda root, a: uc.day(root, str(a.get("date", ""))),
    "period": lambda root, a: uc.period(root, _span(a)),
    "context_show": lambda root, _a: uc.context_show(root),
    "context_for": lambda root, a: uc.context_for(root, str(a.get("task", ""))),
    "context_history": lambda root, _a: uc.context_log(root),
}
