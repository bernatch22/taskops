"""`taskops status` — where the project stands, in one screen.

The command somebody types before they start working, so it is built around costing
nothing: one SQLite file, no git subprocess and no socket. `--fetch` is the single
exception and it has to be asked for by name — a status that quietly did a round trip
would be slow exactly when the network is bad, which is when people run it twice.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import IO

from ....render.prompt import render_porcelain, render_prompt
from ....render.status import render_status
from ....usecases.status import IDLE_DAYS, status
from ._shared import add_target

__all__ = ["register", "run"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("status", help="where the project stands, in one screen")
    add_target(parser)
    parser.add_argument("--actor", default="",
                        help="whose claims count as `yours` (default: the resolved caller)")
    parser.add_argument("--fetch", action="store_true",
                        help="pull from the remote first — the only thing here that "
                             "touches the network")
    parser.add_argument("--idle-days", type=int, default=IDLE_DAYS,
                        help=f"how long an open card may sit untouched (default: {IDLE_DAYS})")
    parser.add_argument("--no-color", action="store_true", help="never emit escape codes")
    parser.add_argument("--prompt", action="store_true",
                        help="one line for a shell prompt or statusline; prints nothing "
                             "and exits 0 outside a project")
    parser.add_argument("--porcelain", action="store_true",
                        help="stable key=value output for scripts (see docs/prompt.md)")
    parser.add_argument("--colour", "--color", default="", choices=("", "zsh"),
                        help="with --prompt: `zsh` emits %%F{..} colour, the default is plain")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    if args.prompt or args.porcelain:
        return _quiet(args)
    return render_status(
        status(str(args.repo), actor=str(args.actor), fetch=bool(args.fetch),
               idle_days=int(args.idle_days)),
        colour=not args.no_color and _colour(sys.stdout))


def _quiet(args: argparse.Namespace) -> str:
    """The prompt path: never the network, and never a word on the way out.

    EVERY failure is swallowed on purpose. This runs inside `precmd`, so a directory that
    is not a project, a database being written by another agent, or a schema from a newer
    version would each put a line of noise above every command the user types — and the
    one thing a prompt segment must never do is make the shell unusable. `--fetch` is
    ignored here for the same reason the budget is 50ms: a prompt does no I/O it can lose.
    """
    try:
        snap = status(str(args.repo), actor=str(args.actor), idle_days=int(args.idle_days))
    except Exception:  # noqa: BLE001 — see the docstring; there is no failure worth printing
        return ""
    if args.porcelain:
        return render_porcelain(snap)
    return render_prompt(snap, colour=str(args.colour))


def _colour(to: IO[str]) -> bool:
    """Decided HERE, never in the renderer, which is pure and takes it as a parameter.

    A status piped into a file with escape codes in it is a bug, so a non-tty gets plain
    text; `NO_COLOR` is honoured because somebody who exported it meant every tool, not
    the ones that remembered to check.
    """
    return bool(getattr(to, "isatty", bool)()) and not os.environ.get("NO_COLOR")
