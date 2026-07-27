"""`taskops ingest commit|branch` — the git hooks. Records, never refuses.

The other half of git-binding. The guard runs BEFORE a commit and can deny; this runs after
one and only records — which is why it also catches every commit the guard never saw: a
human's terminal commit, a `--no-verify`, a rebase landing on a task branch.
"""

from __future__ import annotations

import argparse

from ....usecases import ingest_branch, ingest_commit
from ._shared import add_target, repo_of

__all__ = ["register"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("ingest", help="record a commit or a branch against its task")
    add_target(parser)
    parser.add_argument("what", choices=("commit", "branch"))
    parser.add_argument("ref", nargs="?", default="", help="a sha, or a branch name")
    parser.add_argument("--actor", default="", help="who is calling")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    """Silent when there was nothing to bind.

    A commit on a non-task branch is completely normal — this hook fires on every commit in
    the repository, including the ones taskops has no opinion about — so saying so would put
    a line of noise in front of a developer on every unrelated commit.
    """
    where = repo_of(args)
    if args.what == "branch":
        event = ingest_branch(where, str(args.ref), actor=str(args.actor))
        return f"taskops: {event['task']} on {event['body'].get('branch')}" if event else ""
    event = ingest_commit(where, str(args.ref) or "HEAD", actor=str(args.actor))
    return f"taskops: recorded {str(event['body'].get('sha'))[:12]} on {event['task']}" \
        if event else ""
