"""The CLI, which behaves like git: it connects, it never manages.

    taskops init            a local board in this repo
    taskops join <url>      join one (bare, ?token= or --invite), install the hooks
    taskops remote add <url>  the host this checkout operates, like git's origin
    taskops remote git      the board's OWN git repository, and how to push to it:
                            printed to paste, or --add to wire it here (never origin)
    taskops serve           host boards — an events API, no dashboard
    taskops server init     bootstrap THIS host: its owner and their ssh key
    taskops board create    make a board on a host  ·  board ls, from anywhere
                            with a remote recorded and a key on disk, all of these
                            go BARE: no URL, no --key, no board name
    taskops board push      THIS repo's local board becomes the hosted one
    taskops board pull      the reverse: a hosted board comes down as a SNAPSHOT
                            that stops moving — the host keeps everything
    taskops board rm        take a board OFF a host — refuses to destroy a history
                            this checkout does not hold (--discard-history says so)
    taskops board visibility <host>/<name> public|private   owner only
    taskops board forge <owner>/<repo> [--need push|admin]  owner only — declares the
                            repo AND enrols its collaborators from their published keys
    taskops board forge --clear                             invite-only again
    taskops invite <who>    a single-use link  ·  taskops revoke --key|--invite
    taskops tidy            remove worktrees whose work is already in the trunk
    taskops ui              the dashboard — serves it if nothing is, opens the browser
    taskops hook …          what the git hooks, the Claude hook and git's credential
                            helper call — never a human

Moving a card from the terminal does not exist: that is MCP. v1 grew 35
management commands, each one a second way to do something the tools already
did, and the two ways drifted.
"""

from __future__ import annotations

import sys
import argparse
from typing import Sequence
from pathlib import Path

from . import (
    rm,
    pull as download,
    push as promote,
    admin,
    hooks,
    claude,
    grants,
    parser as flags,
    remote,
    operate,
    serving,
    commands,
    gitremote,
)
from ..board import find_root
from .._errors import TaskopsError
from ..gitwork import trees


def main(argv: Sequence[str] | None = None) -> int:
    """Parse (`parser.py` holds every flag), then dispatch — and turn the one
    error type the whole program raises into a line and an exit code."""
    args = flags.build(__doc__ or "").parse_args(argv)
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
        # `push` and `pull` are each their own module — five ordered steps and a
        # config flip, against `board`'s two one-shot calls — so `main` routes
        # them, and neither imports the other (both need `operate`'s transport
        # and its address parser, and nothing needs them back). `rm` is separated
        # for the mirrored reason: one call, and a guardrail around it that is
        # the whole command.
        action = str(args.action)
        if action == "push":
            return promote.run(args)
        if action == "pull":
            return download.run(args)
        if action == "rm":
            return rm.run(args)
        return operate.board(args)
    if args.command == "invite":
        return grants.invite(args)
    if args.command == "revoke":
        return grants.revoke(args)
    if args.command == "tidy":
        removed = trees.tidy(find_root(here), str(args.trunk))
        print("\n".join(removed) if removed else "nothing to tidy — no integrated worktrees")
        return 0
    if args.command == "ui":
        return serving.ui(here)
    if str(args.which) == "credential":
        # git's credential helper protocol: the operation is argv, the request is
        # stdin. Read here, so `gitremote.credential` stays a pure function of
        # what git said and the tests can hand it a request directly.
        return gitremote.credential(sys.stdin.read(), [str(x) for x in args.rest])
    if str(args.which) == "claude":
        # Routed here and not through `commands` so the delivery hook owns its
        # own error policy end to end: it prints NOTHING, ever, including the
        # `taskops: …` line `main()` writes for every other failure.
        return claude.deliver(here)
    return hooks.hook(here, str(args.which), [str(x) for x in args.rest])
