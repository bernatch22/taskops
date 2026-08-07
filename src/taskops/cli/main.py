"""The CLI, which behaves like git: it connects, it never manages.

    taskops init            a local board in this repo
    taskops join <url>      join one (?token= or ?invite=), install the hooks
    taskops serve           host boards
    taskops invite <who>    a single-use link  ·  --revoke <id>
    taskops tidy            remove worktrees whose work is already in the trunk
    taskops open            the UI in a browser
    taskops hook …          what the two git hooks and the Claude hook call

Moving a card from the terminal does not exist: that is MCP. v1 grew 35
management commands, each one a second way to do something the tools already
did, and the two ways drifted.
"""

from __future__ import annotations

import sys
import argparse
import webbrowser
from typing import Sequence
from pathlib import Path

from . import claude, commands
from ..board import find_root, read_config
from .._errors import TaskopsError
from ..gitwork import trees


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="taskops", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="a local board in this repo")
    join = sub.add_parser("join", help="join a board and install the hooks")
    join.add_argument("url", help="https://host/<board>?token=… or ?invite=…")
    join.add_argument("--as", dest="actor", default="", help="dev:<name> (default: $USER)")
    server = sub.add_parser("serve", help="host boards")
    server.add_argument("--root", default="~/taskops-boards")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8787)
    server.add_argument("--ui", default="")
    invite = sub.add_parser("invite", help="a single-use link for a teammate")
    invite.add_argument("who", nargs="?", default="")
    invite.add_argument("--board", default="")
    invite.add_argument("--root", default="~/taskops-boards")
    invite.add_argument("--revoke", default="", help="a credential id")
    tidy = sub.add_parser("tidy", help="remove integrated worktrees and branches")
    tidy.add_argument("--trunk", default="")
    sub.add_parser("open", help="the UI in a browser")
    hook = sub.add_parser("hook", help="internal: what the installed hooks call")
    hook.add_argument("which", choices=["trailer", "commit", "claude"])
    hook.add_argument("rest", nargs="*")

    args = parser.parse_args(argv)
    try:
        return _run(args)
    except TaskopsError as err:
        print(f"taskops: {err}", file=sys.stderr)
        return 1


def _run(args: argparse.Namespace) -> int:
    here = Path.cwd()
    if args.command == "init":
        return commands.init(here)
    if args.command == "join":
        return commands.join(here, str(args.url), str(args.actor))
    if args.command == "serve":
        return commands.serve(args)
    if args.command == "invite":
        return commands.invite(args)
    if args.command == "tidy":
        removed = trees.tidy(find_root(here), str(args.trunk))
        print("\n".join(removed) if removed else "nothing to tidy — no integrated worktrees")
        return 0
    if args.command == "open":
        url = str(read_config(find_root(here)).get("url", ""))
        if not url:
            print(
                "this project has no remote board — run `taskops serve` and open it",
                file=sys.stderr,
            )
            return 1
        webbrowser.open(f"{url}/ui/")
        return 0
    if str(args.which) == "claude":
        # Routed here and not through `commands` so the delivery hook owns its
        # own error policy end to end: it prints NOTHING, ever, including the
        # `taskops: …` line `main()` writes for every other failure.
        return claude.deliver(here)
    return commands.hook(here, str(args.which), [str(x) for x in args.rest])
