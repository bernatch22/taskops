"""The CLI, which behaves like git: it connects, it never manages.

    taskops init            a local board in this repo
    taskops join <url>      join one (?token= or ?invite=), install the hooks
    taskops serve           host boards — an events API, no dashboard
    taskops server init     bootstrap THIS host: its owner and their ssh key
    taskops invite <who>    a single-use link  ·  --revoke <id>
    taskops tidy            remove worktrees whose work is already in the trunk
    taskops ui              the dashboard — serves it if nothing is, opens the browser
    taskops hook …          what the two git hooks and the Claude hook call

Moving a card from the terminal does not exist: that is MCP. v1 grew 35
management commands, each one a second way to do something the tools already
did, and the two ways drifted.
"""

from __future__ import annotations

import sys
import argparse
from typing import Sequence
from pathlib import Path

from . import admin, claude, serving, commands
from ..board import find_root
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
    host = sub.add_parser("server", help="operate this HOST (over ssh, once): its owner")
    host.add_argument("action", choices=["init"])
    host.add_argument("--root", default="~/taskops-boards")
    host.add_argument("--key", default="", help="the owner's pubkey: a path, or - for stdin")
    host.add_argument("--owner", default="", help="the owner's name (default: $USER)")
    invite = sub.add_parser("invite", help="a single-use link for a teammate")
    invite.add_argument("who", nargs="?", default="")
    invite.add_argument("--board", default="")
    invite.add_argument("--root", default="~/taskops-boards")
    invite.add_argument("--revoke", default="", help="a credential id")
    tidy = sub.add_parser("tidy", help="remove integrated worktrees and branches")
    tidy.add_argument("--trunk", default="")
    sub.add_parser("ui", help="the dashboard: serve if needed, open the browser, token included")
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
        return serving.serve(args)
    if args.command == "server":
        return admin.server(args)
    if args.command == "invite":
        return serving.invite(args)
    if args.command == "tidy":
        removed = trees.tidy(find_root(here), str(args.trunk))
        print("\n".join(removed) if removed else "nothing to tidy — no integrated worktrees")
        return 0
    if args.command == "ui":
        return serving.ui(here)
    if str(args.which) == "claude":
        # Routed here and not through `commands` so the delivery hook owns its
        # own error policy end to end: it prints NOTHING, ever, including the
        # `taskops: …` line `main()` writes for every other failure.
        return claude.deliver(here)
    return commands.hook(here, str(args.which), [str(x) for x in args.rest])
