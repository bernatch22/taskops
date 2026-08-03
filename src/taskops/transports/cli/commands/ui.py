"""`taskops ui` — the live board, and its API, on one port."""

from __future__ import annotations

import argparse
import os
import sys

from ....transports.http import Policy, bound_port, build_server
from ....usecases import locate
from ....usecases.localui import forget_ui, note_ui
from ._shared import add_target, repo_of

__all__ = ["register"]

DEFAULT_PORT = 2140

_HELP = "serve the live web interface (board, activity, reports)"


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    """Two parsers, one `run`.

    `studio` was the name until the web interface stopped being one screen, and a command in
    somebody's shell history — or in a script, or a README they already wrote — must not start
    failing because we renamed it. The alias registers with no `help`, so it never appears in
    `taskops --help`: it is a bridge for existing muscle memory, not a second documented way in.
    """
    _flags(sub.add_parser("ui", help=_HELP))
    _flags(sub.add_parser("studio")).set_defaults(deprecated_name=True)


def _flags(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Every flag on both parsers, from one place — an alias that drifted on `--readonly`
    would be worse than no alias at all."""
    add_target(parser)
    parser.add_argument("--host", default="127.0.0.1",
                        help="bind address (default: loopback only)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--token", default=os.environ.get("TASKOPS_API_TOKEN", ""),
                        help="require `Authorization: Bearer <token>` ($TASKOPS_API_TOKEN)")
    parser.add_argument("--readonly", action="store_true",
                        help="refuse every write — for a board on a shared screen")
    parser.add_argument("--rate-limit", type=int, default=0, dest="rate_limit",
                        help="requests per minute, 0 for none")
    parser.set_defaults(run=run, deprecated_name=False)
    return parser


def run(args: argparse.Namespace) -> str:
    """Blocks until interrupted.

    The banner goes to STDERR so it stays visible when stdout is redirected, and it is the only
    thing this command prints — the request log is silenced in the handler, or the URL a person
    needs would scroll away under the board's own polling. The deprecation line joins it there
    for the same reason: it is a note to a human, never part of the output.
    """
    if getattr(args, "deprecated_name", False):
        print("taskops studio is now taskops ui", file=sys.stderr)
    root = locate(repo_of(args))
    policy = Policy(token=args.token, readonly=bool(args.readonly),
                    rate_limit=int(args.rate_limit))
    server = build_server(str(args.host), int(args.port), root, policy)
    # WRITTEN AFTER THE BIND, never before: the note says "a board is answering on this port",
    # and one written on intent would advertise a port that a bind error was about to leave
    # dead. `--port 0` is how anything that starts this detached asks the OS for a free one.
    note_ui(root, bound_port(server))
    print(f"taskops ui → http://{args.host}:{bound_port(server)}/  ({root})"
          + ("  [token required]" if args.token else "")
          + ("  [read-only]" if args.readonly else ""), file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped", file=sys.stderr)
    finally:
        server.server_close()
        forget_ui(root)
    return ""
