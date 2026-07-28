"""`taskops run` — the spawn path, under the name that says what it does.

The capability existed as `dispatch --spawn`, which is how a flag hides a decision: a person
scanning the help had no way to tell that one word turns a free preparation into N NEW billed
Claude sessions. Same code, honest name, and the price stated BEFORE anything starts rather
than on the invoice.

`--yes` exists because a fleet script cannot answer a prompt. Everything else that reads a
board is free; this is the one command that is not, so an unattended caller has to say so.
"""

from __future__ import annotations

import argparse
import sys

from .dispatch import add_dispatch_args, dispatch_with

__all__ = ["register", "WARNING"]

WARNING = ("⚠ each worker is a NEW billed Claude session — for free parallelism dispatch "
           "sub-agents from a session (taskops_dispatch)")


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("run",
                            help="run cards with headless Claude workers (experimental, billed)")
    add_dispatch_args(parser)
    parser.add_argument("--yes", action="store_true",
                        help="skip the confirmation (for unattended callers)")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    """Warn, confirm, then spawn. A dry run is free, so it skips both."""
    if not args.dry_run and not _confirmed(bool(args.yes)):
        return "aborted — nothing started"
    return dispatch_with(args, spawn=True)


def _confirmed(yes: bool) -> bool:
    """The warning goes to stderr so a piped render stays a render; the answer comes from
    stdin, and no tty (a hook, a CI job) counts as "did not agree" rather than as yes."""
    print(WARNING, file=sys.stderr)
    if yes:
        return True
    try:
        return input("start them? [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False
