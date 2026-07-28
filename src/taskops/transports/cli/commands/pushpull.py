"""`taskops push` and `taskops pull` — sync against the remote instead of through git.

Two commands in one module because they are one summary: both print the same four numbers,
and a second module would be a second place to keep that sentence honest.

A conflicted report is printed on its OWN line, after the summary, and the exit code stays 0.
Nothing was lost — the refusal is the point — so this is a decision waiting for a person, not
a failure; making it exit non-zero would break the `push && git push` line everyone writes.
"""

from __future__ import annotations

import argparse

from ....usecases import Exchange
from ....usecases import pull as receive
from ....usecases import push as send
from ._shared import add_target, repo_of

__all__ = ["register"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    pushing = sub.add_parser("push", help="send this board to the remote, then take theirs")
    add_target(pushing)
    pushing.add_argument("--force", action="store_true",
                         help="overwrite a report the server refused to replace "
                              "(whatever narration is on the server is lost)")
    pushing.set_defaults(run=run_push)
    pulling = sub.add_parser("pull", help="take the remote's events and reports")
    add_target(pulling)
    pulling.set_defaults(run=run_pull)


def run_push(args: argparse.Namespace) -> str:
    return _summary("pushed", send(repo_of(args), force=bool(args.force)))


def run_pull(args: argparse.Namespace) -> str:
    return _summary("pulled", receive(repo_of(args)))


def _summary(verb: str, done: Exchange) -> str:
    """Events both ways, reports both ways, then every stand-off in full."""
    swap = done.reports
    parts = [f"{done.accepted} event(s) out", f"{done.events_in} in"]
    if done.unblocked:
        parts.append(f"{len(done.unblocked)} now ready")
    if swap.uploaded or swap.downloaded:
        parts.append(f"reports {len(swap.uploaded)} up, {len(swap.downloaded)} down")
    lines = [f"{verb}: " + ", ".join(parts)]
    lines += [f"  ! {clash}" for clash in swap.conflicts]
    return "\n".join(lines)
