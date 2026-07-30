"""`taskops publish` — push every task branch, so a reviewer on another machine can see it."""

from __future__ import annotations

import argparse

from ....usecases.publish import publish_all
from ._shared import add_target, repo_of

__all__ = ["register", "run"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("publish", help="push every tk/ branch to origin — the repair for "
                                            "work stranded on one machine")
    add_target(parser)
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    landed = publish_all(repo_of(args))
    if not landed:
        return ("nothing to publish — every task branch is already on the remote, or this "
                "project has no origin")
    return "\n".join([f"published {len(landed)} branch(es):", *(f"  {b}" for b in landed)])
