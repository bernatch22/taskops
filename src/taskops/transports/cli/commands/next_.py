"""`taskops next` — claim work from a terminal. The same call the MCP tool makes."""

from __future__ import annotations

import argparse

from ....render import render_next
from ....usecases import next_task
from ._shared import add_identity, add_target, repo_of

__all__ = ["register"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("next", help="claim the next available task")
    add_target(parser)
    add_identity(parser)
    parser.add_argument("--labels", default="", help="comma-separated labels to restrict to")
    parser.add_argument("--task", default="", help="claim this task instead of choosing")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    labels = tuple(p.strip() for p in str(args.labels).split(",") if p.strip())
    return render_next(next_task(repo_of(args), actor=args.actor, session=args.session,
                                 labels=labels, task=args.task))
