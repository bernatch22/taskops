"""Handlers that CHANGE the board: plan, claim, update, dispatch, recover.

Split from `_handlers` because there are seven tools and one file of them stopped being readable. The
seam is what a handler DOES: every one of these writes, so each is the entry point of a use case that enforces a rule —
a guard, a lease, an assignment — and none of them may make that decision here.
"""

from __future__ import annotations

from typing import Any

from ...render import (
    render_capture,
    render_dispatch,
    render_next,
    render_plan,
    render_recover,
    render_update,
)
from ...usecases import (
    capture,
    dispatch,
    next_task,
    plan,
    recover,
    update,
)
from ...usecases._project import attributed
from . import arguments as arg

__all__ = ["plan_", "capture_", "next_", "update_", "dispatch_", "recover_"]


def plan_(args: dict[str, Any]) -> str:
    return render_plan(plan(arg.repo(args), arg.entries(args),
                            actor=arg.optional(args, "actor")))


def capture_(args: dict[str, Any]) -> str:
    return render_capture(capture(
        arg.repo(args), arg.text(args, "title"), spec=arg.optional(args, "spec"),
        files=arg.optional(args, "files"), labels=arg.optional(args, "labels"),
        acceptance=args.get("acceptance"), priority=args.get("priority"),
        claim=bool(args.get("claim", True)), assign=arg.optional(args, "assign"),
        actor=arg.optional(args, "actor"), session=arg.optional(args, "session")))


def next_(args: dict[str, Any]) -> str:
    """A card asked for BY ID speaks for itself — see `usecases._project.attributed`. A pool
    call passes `task=""` and is left to resolve exactly as it does today."""
    repo, task = arg.repo(args), arg.optional(args, "task")
    return render_next(next_task(repo, actor=attributed(repo, task, arg.optional(args, "actor")),
                                 session=arg.optional(args, "session"),
                                 labels=arg.csv(args, "labels"), task=task))


def update_(args: dict[str, Any]) -> str:
    """The call the specialists kept losing their identity on: `next` carried an actor and the
    update after it did not. `update` always names a task, so the card can always answer."""
    repo, task = arg.repo(args), arg.text(args, "task")
    return render_update(update(repo, task,
                                actor=attributed(repo, task, arg.optional(args, "actor")),
                                status=arg.optional(args, "status"),
                                comment=arg.optional(args, "comment"),
                                mentions=arg.csv(args, "mentions"),
                                blocked_on=arg.optional(args, "blocked_on"),
                                no_code=arg.flag(args, "no_code"),
                                # These two were NOT forwarded, and the omission cost a whole
                                # live run: every close carrying evidence failed "nothing says
                                # they were met" — the field crossed the wire and died here,
                                # one line short of the engine.
                                evidence=arg.optional(args, "evidence"),
                                no_evidence=arg.optional(args, "no_evidence")))


def dispatch_(args: dict[str, Any]) -> str:
    return render_dispatch(dispatch(arg.repo(args), tasks=arg.csv(args, "tasks"),
                                    count=arg.count(args), actor=arg.optional(args, "actor"),
                                    prefix=arg.optional(args, "prefix"),
                                    dry_run=arg.flag(args, "dry_run")))


def recover_(args: dict[str, Any]) -> str:
    """`grace` of 0 means "use the default", which is what an omitted integer reads as."""
    from ..._clock import HEARTBEAT_GRACE

    asked = arg.count(args, "grace")
    return render_recover(recover(arg.repo(args), actor=arg.optional(args, "actor"),
                                  force=arg.flag(args, "force"),
                                  grace=float(asked) or HEARTBEAT_GRACE))

