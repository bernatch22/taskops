"""Handlers that CHANGE the board: plan, claim, update, dispatch, recover.

Split from `_handlers` because there are seven tools and one file of them stopped being readable. The
seam is what a handler DOES: every one of these writes, so each is the entry point of a use case that enforces a rule —
a guard, a lease, an assignment — and none of them may make that decision here.
"""

from __future__ import annotations

from typing import Any

from ...render import (
    render_dispatch,
    render_next,
    render_plan,
    render_recover,
    render_update,
)
from ...usecases import (
    dispatch,
    next_task,
    plan,
    recover,
    update,
)
from . import arguments as arg

__all__ = ["plan_", "next_", "update_", "dispatch_", "recover_"]


def plan_(args: dict[str, Any]) -> str:
    return render_plan(plan(arg.repo(args), arg.entries(args),
                            actor=arg.optional(args, "actor")))


def next_(args: dict[str, Any]) -> str:
    return render_next(next_task(arg.repo(args), actor=arg.optional(args, "actor"),
                                 session=arg.optional(args, "session"),
                                 labels=arg.csv(args, "labels"),
                                 task=arg.optional(args, "task")))


def update_(args: dict[str, Any]) -> str:
    return render_update(update(arg.repo(args), arg.text(args, "task"),
                                actor=arg.optional(args, "actor"),
                                status=arg.optional(args, "status"),
                                comment=arg.optional(args, "comment"),
                                mentions=arg.csv(args, "mentions"),
                                blocked_on=arg.optional(args, "blocked_on"),
                                no_code=arg.flag(args, "no_code")))


def dispatch_(args: dict[str, Any]) -> str:
    return render_dispatch(dispatch(arg.repo(args), tasks=arg.csv(args, "tasks"),
                                    count=arg.count(args), actor=arg.optional(args, "actor"),
                                    prefix=arg.optional(args, "prefix"),
                                    model=arg.optional(args, "model"),
                                    # `spawn` is NOT read, on purpose: this surface never starts a
                                    # process. See `DispatchParams` for why.
                                    dry_run=arg.flag(args, "dry_run")))


def recover_(args: dict[str, Any]) -> str:
    """`grace` of 0 means "use the default", which is what an omitted integer reads as."""
    from ..._clock import HEARTBEAT_GRACE

    asked = arg.count(args, "grace")
    return render_recover(recover(arg.repo(args), actor=arg.optional(args, "actor"),
                                  force=arg.flag(args, "force"),
                                  grace=float(asked) or HEARTBEAT_GRACE))


