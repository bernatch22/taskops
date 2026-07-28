"""`ingest commit|branch` and `sync` — what git tells taskops after the fact.

The other half of git-binding. `commit` runs BEFORE a commit and can deny; `ingest` runs after
one and only records — which is why it also catches every commit the guard never saw: a
human's terminal commit, a `--no-verify`, a rebase landing on a task branch.

`sync` is here rather than left on the developer's CLI for one reason: `post-merge` is a git
hook line, and a git hook line may not enter through the door a person types. `taskops sync`
still exists for the person, reaching the same use case; this is the same call with its
report thrown away, because git redirects the hook's output to /dev/null anyway.
"""

from __future__ import annotations

import argparse

from ...usecases import ingest_branch, ingest_commit
from ...usecases import sync as reconcile
from ._args import add_target, repo_of

__all__ = ["register"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("ingest", help="record a commit or a branch against its task")
    add_target(parser)
    parser.add_argument("what", choices=("commit", "branch"))
    parser.add_argument("ref", nargs="?", default="", help="a sha, or a branch name")
    parser.set_defaults(run=run)

    merged = sub.add_parser("sync", help="import what a merge just brought in (post-merge)")
    add_target(merged)
    merged.set_defaults(run=run_sync)


def run(args: argparse.Namespace) -> str:
    """Silent when there was nothing to bind.

    A commit on a non-task branch is completely normal — this hook fires on every commit in
    the repository, including the ones taskops has no opinion about — so saying so would put a
    line of noise in front of a developer on every unrelated commit.
    """
    where = repo_of(args)
    if args.what == "branch":
        event = ingest_branch(where, str(args.ref), actor=str(args.actor))
        return f"taskops: {event['task']} on {event['body'].get('branch')}" if event else ""
    event = ingest_commit(where, str(args.ref) or "HEAD", actor=str(args.actor))
    return f"taskops: recorded {str(event['body'].get('sha'))[:12]} on {event['task']}" \
        if event else ""


def run_sync(args: argparse.Namespace) -> str:
    """Silent by design: the report belongs to `taskops sync`, which a person reads."""
    reconcile(repo_of(args))
    return ""
