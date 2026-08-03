"""`taskops statusline` — the row Claude Code renders at the bottom of a session.

Not a hook, which is why it is here and not in `transports/hooks`: a hook answers with a JSON
object on stdout and taskops decides what the harness does with it. A status line answers with
**text**, and the harness paints it. Same integration, opposite direction, so wiring it into
`taskops-hook` would have meant one entry point with two output contracts.

It READS stdin the way a hook does — Claude Code writes the session JSON there — but never
requires it: run by hand in a terminal, stdin is a tty and the payload is `{}`, which prints
the board half of the row. That is the difference between a command somebody can try and a
command that hangs when they do.

**Never fails loudly.** This runs on a 300 ms debounce, so an exception here would be an error
message flashing at the bottom of the screen on every keystroke. Nothing to say prints nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, cast

from ....render.statusline import render_statusline
from ....usecases.statusline import statusline
from ._shared import add_actor, add_target, repo_of

__all__ = ["register", "run"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("statusline",
                            help="the Claude Code status line for this board (stdin JSON)")
    add_target(parser)
    add_actor(parser)
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    """The row, or "" for anything that is not a taskops project.

    Silence and not a complaint: this command is configured once, in `settings.json`, and then
    runs in every session in every repository that person opens. A line saying "no board here"
    would be permanent furniture in all the ones that do not have one.
    """
    payload = _stdin()
    try:
        bar = statusline(repo_of(args), actor=str(args.actor))
    except Exception:  # noqa: BLE001 — a footer must never be an error message, see the module
        return ""
    return render_statusline(bar, payload)


def _stdin() -> dict[str, Any]:
    """The session payload, or `{}` for a tty, a pipe that closed, or anything unparseable."""
    if sys.stdin.isatty():
        return {}
    try:
        parsed: object = json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, OSError, ValueError):
        return {}
    return cast("dict[str, Any]", parsed) if isinstance(parsed, dict) else {}
