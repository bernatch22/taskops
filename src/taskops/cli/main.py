"""The CLI, which behaves like git: it connects, it never manages.

    taskops init            a local board in this repo
    taskops join <url>      join one (?token= or ?invite=), install the hooks
    taskops remote add <url>  the host this checkout operates, like git's origin
    taskops serve           host boards — an events API, no dashboard
    taskops server init     bootstrap THIS host: its owner and their ssh key
    taskops board create    make a board on a host  ·  board ls, from anywhere
                            with a remote recorded and a key on disk, all of these
                            go BARE: no URL, no --key, no board name
    taskops board push      THIS repo's local board becomes the hosted one
    taskops board rm        take a board OFF a host — refuses to destroy a history
                            this checkout does not hold (--discard-history says so)
    taskops board visibility <host>/<name> public|private   owner only
    taskops invite <who>    a single-use link  ·  taskops revoke --key|--invite
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

from . import rm, push as promote, admin, claude, remote, operate, serving, commands
from ..board import find_root
from .._errors import TaskopsError
from ..gitwork import trees

AS_HELP = "the principal that key belongs to (default: $USER)"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="taskops", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="a local board in this repo")
    join = sub.add_parser("join", help="join a board and install the hooks")
    join.add_argument(
        "url",
        nargs="?",
        default="",
        help="<name>, <host>/<name>, or nothing (the recorded/directory name) — "
        "a full https:// URL with ?token= or ?invite= keeps working",
    )
    join.add_argument("--as", dest="actor", default="", help="dev:<name> (default: $USER)")
    join.add_argument(
        "--invite",
        default="",
        help="first join: the single-use id from `taskops invite` — your key is enrolled with it",
    )
    join.add_argument(
        "--discard-local",
        action="store_true",
        help="a local board here is archived instead of orphaned by the join",
    )
    join.add_argument(
        "--key",
        default="",
        help="overrides the discovered ssh key (its .pub is what gets registered)",
    )
    origin = sub.add_parser("remote", help="the host this checkout operates (git's origin)")
    origin.add_argument("action", nargs="?", default="", choices=["", "add"])
    origin.add_argument("url", nargs="?", default="", help="https://<host>")
    origin.add_argument(
        "--replace", action="store_true", help="this checkout already names another host"
    )
    server = sub.add_parser("serve", help="host boards")
    server.add_argument("--root", default="~/taskops-boards")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8787)
    host = sub.add_parser("server", help="operate this HOST (over ssh, once): its owner")
    host.add_argument("action", choices=["init"])
    host.add_argument("--root", default="~/taskops-boards")
    host.add_argument("--key", default="", help="the owner's pubkey: a path, or - for stdin")
    host.add_argument("--owner", default="", help="the owner's name (default: $USER)")
    boards = sub.add_parser("board", help="create or list the boards on a host")
    boards.add_argument("action", choices=["create", "ls", "push", "rm", "visibility"])
    boards.add_argument("target", nargs="?", default="", help="<host>/<name>, or just <name>")
    boards.add_argument(
        "visibility",
        nargs="?",
        default="",
        choices=["", "public", "private"],
        help="visibility: public means ANONYMOUS READ — writing always needs a key",
    )
    boards.add_argument("--key", default="", help="the ssh key that signs you in")
    boards.add_argument("--invite", default="", help="push: register that key first")
    # NOT `--force`, and never an alias for one (ARCHITECTURE.md §11): the flag
    # that destroys a history has to name the history.
    boards.add_argument(
        "--discard-history",
        action="store_true",
        help="board rm: destroy a history this checkout does not hold — say so out loud",
    )
    boards.add_argument("--as", dest="principal", default="", help=AS_HELP)
    invite = sub.add_parser("invite", help="a single-use link for a teammate")
    invite.add_argument("who", nargs="?", default="")
    invite.add_argument("--board", default="")
    invite.add_argument("--host", default="", help="the server (default: the one you joined)")
    invite.add_argument("--key", default="", help="the ssh key that signs you in")
    invite.add_argument("--as", dest="principal", default="", help=AS_HELP)
    # `--root` is BREAK-GLASS and so it has no default: passing it is the deliberate
    # choice to work on the files, on the box, when the API is what broke.
    invite.add_argument("--root", default="", help="break-glass: the boards dir, ON the host")
    kill = sub.add_parser("revoke", help="a key or an invite stops working")
    kill.add_argument("--key", default="", help="a fingerprint: SHA256:…")
    kill.add_argument("--invite", default="", help="a credential id")
    kill.add_argument("--host", default="")
    # NOT `--key`: on this verb that word is already the fingerprint being revoked.
    kill.add_argument("--sign-key", default="", help="the ssh key that signs YOU in")
    kill.add_argument("--as", dest="principal", default="", help=AS_HELP)
    kill.add_argument("--root", default="", help="break-glass: the boards dir, ON the host")
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
        return commands.join(
            here,
            str(args.url),
            str(args.actor),
            str(args.key),
            bool(args.discard_local),
            str(args.invite),
        )
    if args.command == "remote":
        return remote.remote(args)
    if args.command == "serve":
        return serving.serve(args)
    if args.command == "server":
        return admin.server(args)
    if args.command == "board":
        # `push` is its own module — five ordered steps and a config flip, against
        # `board`'s two one-shot calls — so `main` routes it, and neither imports
        # the other (`push.py` needs `operate`'s transport and its address parser).
        # `rm` is separated for the mirrored reason: one call, and a guardrail
        # around it that is the whole command.
        action = str(args.action)
        if action == "push":
            return promote.run(args)
        if action == "rm":
            return rm.run(args)
        return operate.board(args)
    if args.command == "invite":
        return operate.invite(args)
    if args.command == "revoke":
        return operate.revoke(args)
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
