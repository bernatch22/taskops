"""`taskops studio` — the live board, and its API, on one port."""

from __future__ import annotations

import argparse
import os
import sys

from ....transports.http import Policy, bound_port, build_server
from ....usecases import locate
from ._shared import add_target, repo_of

__all__ = ["register"]

DEFAULT_PORT = 2140


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("studio", help="serve the live board and the JSON API")
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
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    """Blocks until interrupted.

    The banner goes to STDERR so it stays visible when stdout is redirected, and it is the only
    thing this command prints — the request log is silenced in the handler, or the URL a person
    needs would scroll away under the board's own polling.
    """
    root = locate(repo_of(args))
    policy = Policy(token=args.token, readonly=bool(args.readonly),
                    rate_limit=int(args.rate_limit))
    server = build_server(str(args.host), int(args.port), root, policy)
    print(f"taskops studio → http://{args.host}:{bound_port(server)}/  ({root})"
          + ("  [token required]" if args.token else "")
          + ("  [read-only]" if args.readonly else ""), file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped", file=sys.stderr)
    finally:
        server.server_close()
    return ""
