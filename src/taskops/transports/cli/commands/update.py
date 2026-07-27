"""`taskops update` — a transition, a comment, a mention. The write path from a terminal."""

from __future__ import annotations

import argparse

from ....render import render_update
from ....usecases import update as apply
from ._shared import add_target, repo_of

__all__ = ["register"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("update", help="change a task's status, or comment on it")
    add_target(parser)
    parser.add_argument("task", help="the task id")
    parser.add_argument("--actor", default="", help="who is calling")
    parser.add_argument("--status", default="",
                        help="in_progress | blocked | review | done | released | cancelled")
    parser.add_argument("--comment", default="", help="what happened, for the thread")
    parser.add_argument("--mentions", default="", help="comma-separated actor ids to notify")
    parser.add_argument("--blocked-on", default="", dest="blocked_on",
                        help="a task id that must finish first")
    parser.add_argument("--no-code", action="store_true", dest="no_code",
                        help="this task legitimately produces no commit")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    mentions = tuple(p.strip() for p in str(args.mentions).split(",") if p.strip())
    return render_update(apply(repo_of(args), str(args.task), actor=args.actor,
                               status=args.status, comment=args.comment,
                               mentions=mentions, blocked_on=args.blocked_on,
                               no_code=bool(args.no_code)))
