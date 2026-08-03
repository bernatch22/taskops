"""The rpc registry — the whitelist of verbs a clone may run in this store.

Split from `rpc` when the table outgrew the module budget, and the split says what each half
is: `rpc` is the DOOR (parse, refuse, guard), this is the LIST. A new remote-safe verb is one
row here; a verb that stays off this list stays local, which is the security posture.

The rows that need more than a lambda live in `_verbargs`, for the same reason and one more:
this table hit the budget with a verb still to add, and a list nobody can append to without
deleting something has stopped being a list of what the surface is.

**Every verb answers with a JSON OBJECT, never a bare array.** The client decoder returns `{}`
for anything that is not an object — deliberately, because an nginx in front of this server
answers 502 in HTML and a reader wants the status rather than a parser traceback. The cost is
that a verb returning a list decodes to nothing, silently: `search` and `context_history` both
did, so on a board with a remote, searching found zero tasks and `context log` was empty, with
no error anywhere. Wrapping is the price of that decoder, so the wrappers live here, on the row,
where the next list-returning verb will see them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ... import usecases as uc
from ...usecases.ingest import bind
from ...usecases.pick import pick
from ._verbargs import assigned as _assigned
from ._verbargs import recovered as _recovered
from ._verbargs import span as _span
from ._verbargs import strings as _strings
from ._verbms import MILESTONE_VERBS

__all__ = ["VERBS", "Verb"]

Verb = Callable[[Path, dict[str, Any]], Any]

VERBS: dict[str, Verb] = {
    **MILESTONE_VERBS,

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
    "context_state": lambda root, a: uc.context_state(
        root, str(a.get("sort", "")), str(a.get("text", "")), labels=_strings(a, "labels"),
        files=_strings(a, "files"), horizon=str(a.get("horizon", "")),
        owner=str(a.get("owner", "")), level=str(a.get("level", "milestone")),
        actor=str(a.get("actor", ""))),
    "context_retire": lambda root, a: uc.context_retire(root, str(a.get("id", "")),
                                                     actor=str(a.get("actor", ""))),
    "policy_set": lambda root, a: uc.set_policy(root, str(a.get("name", "")),
                                                str(a.get("value", "")),
                                                actor=str(a.get("actor", ""))),
    # reads — served from the one store every write above landed in
    "ask": lambda root, a: uc.ask(root, str(a.get("task", "")), actor=str(a.get("actor", ""))),
    "inbox": lambda root, a: uc.inbox(root, actor=str(a.get("actor", ""))),
    "search": lambda root, a: {"tasks": uc.search(root, str(a.get("query", "")),
                                                  limit=int(a.get("limit", 20) or 20))},
    "attention": lambda root, a: uc.attention(root, actor=str(a.get("actor", ""))),
    "landed": lambda root, a: uc.note_landing(
        root, task=str(a.get("task", "")), ok=bool(a.get("ok")), why=str(a.get("why", "")),
        trunk=str(a.get("trunk", "")), sha=str(a.get("sha", "")),
        actor=str(a.get("actor", ""))),
    "team": lambda root, a: uc.team_now(root, actor=str(a.get("actor", "")),
                                        session=str(a.get("session", ""))),
    "board": lambda root, _a: uc.board(root),
    "standup": lambda root, a: uc.standup(root, since=str(a.get("since", "")) or "24h",
                                       actor=str(a.get("actor", ""))),
    "day": lambda root, a: uc.day(root, str(a.get("date", ""))),
    "period": lambda root, a: uc.period(root, _span(a)),
    "context_show": lambda root, a: uc.context_show(root, mine=bool(a.get("mine"))),
    "context_for": lambda root, a: uc.context_for(root, str(a.get("task", ""))),
    "context_history": lambda root, _a: {"facts": uc.context_log(root)},
    "policy_show": lambda root, _a: {"policies": uc.policy_show(root)},
}
