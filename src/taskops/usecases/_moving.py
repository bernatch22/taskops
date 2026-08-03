"""The one door every state change of a chapter goes through, and how an id is resolved.

Split from `milestone` on its budget, and the split says what each half is: that module is the
VERB SET a person or an agent reaches for, this is the plumbing all seven share — resolve the id,
ask the machine, append one event, read it back.

Routing happens HERE and before the store is opened. On a board with a remote the server holds
the only log that matters, so a move applied locally would be a chapter that closed on one
machine and stayed open everywhere else — which is the failure the whole routing layer exists to
prevent, and it is one `with project(...)` away from happening by accident.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from .._errors import BadRequest
from .._types import EventKind
from ..contracts.context import CONTEXT_TASK
from ..contracts.milestone import MILESTONE_KIND, Milestone, MilestoneState
from ..engine import record
from ..engine.milestones import move as legal
from ..storage import Store
from ..storage._prefix import matching
from ..storage.milestone import milestones, one
from ._project import caller, heartbeat, project
from ._routing import call_remote, whoami

__all__ = ["written", "moved", "need", "as_milestone", "TASK"]

TASK = CONTEXT_TASK
"""The sentinel a milestone event is filed under. An `Event` must name a task and a chapter is
about the project, so it shares the one context already uses — `of_task("project")` is then the
whole story of a board in one indexed read."""

_KIND = cast("EventKind", MILESTONE_KIND)
"""`EventKind` is a Literal in layer 0 and this module may not widen it, so the cast names the one
place this kind enters the log — the same shape `usecases.context` uses for its own."""


def written(start_at: Path | str, body: dict[str, Any], actor: str) -> Milestone:
    """Append a `create` and read the chapter back. Its id IS the event's — a content hash, so a
    fact written on one clone can attach to a chapter created on another."""
    with project(start_at) as store:
        who = caller(store, actor)["id"]
        heartbeat(store, who)
        event = record(store, task=TASK, actor=who, kind=_KIND, body=body)
        return need(store, event["id"])


def moved(start_at: Path | str, wanted: str, to: MilestoneState, *, note: str = "",
          carry: tuple[str, ...] = (), into: str = "", actor: str = "") -> Milestone:
    """Every state change, through one door. The machine decides; this resolves and appends.

    ROUTED FIRST, before the store is opened: on a board with a remote the server holds the only
    log that matters, and a move applied locally would be a chapter that closed on one machine.
    """
    verb = {"reached": "milestone_done", "abandoned": "milestone_cancel",
            "review": "milestone_review"}.get(to, "milestone_move")
    if (answer := call_remote(start_at, verb,
                              {"milestone": wanted, "to": to, "m": note,
                               "carry": list(carry), "into": into,
                               "actor": whoami(start_at, actor)})) is not None:
        return as_milestone(answer)
    with project(start_at) as store:
        found = need(store, wanted)
        who = caller(store, actor)["id"]
        if (refusal := legal(found["state"], to, who, note=note, milestone=found["id"])):
            raise BadRequest(refusal)
        heartbeat(store, who)
        record(store, task=TASK, actor=who, kind=_KIND,
               body={"op": "move", "milestone": found["id"], "to": to, "m": note.strip(),
                     "carry": list(carry), "into": into})
        return need(store, found["id"])


def need(store: Store, wanted: str) -> Milestone:
    """The chapter that string names, or the refusal that says why it names none.

    A PREFIX is accepted for the same reason `context retire` accepts one: every renderer prints
    eight characters, so the string a person can see was the one string this refused.
    """
    asked = wanted.strip()
    if not asked:
        raise BadRequest("which milestone? `taskops milestone list` prints their ids")
    if (found := one(store, asked)) is not None:
        return found
    hits = matching(milestones(store), asked)
    raise BadRequest(f"`{asked}` names {len(hits)} milestones — `taskops milestone list` prints "
                     f"them, and the eight characters it shows are enough to name one")


def as_milestone(answer: Any) -> Milestone:
    """What the server sent back. Unwrapped when the verb answered `{"milestone": {…}}`, because
    an rpc verb answers an OBJECT and never a bare value — the decoder drops anything else."""
    if isinstance(answer, dict) and "milestone" in answer:
        return cast("Milestone", answer["milestone"])
    return cast("Milestone", answer)
