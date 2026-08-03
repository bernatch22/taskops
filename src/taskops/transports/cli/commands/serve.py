"""`taskops serve` — many projects' boards on one port, each behind its own token.

`taskops ui` serves the repository you are standing in; this serves a DIRECTORY OF PROJECTS and
is the thing meant to sit on a host. The difference that matters is not the routing — see
`transports.http.projects` for that — it is the trust model: there is no ambient "it's only
loopback" here, so every project has a secret and a project without one is not served.

It runs no git hooks and no guard, and `serve init` creates the project with
`install_git_hooks=False`: this is a store of boards, not a working tree. The code stays in git
where it belongs; what centralises is the board, so that two agents racing for the same task
compete inside ONE sqlite.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ....transports.http import bound_port, mount, serve_route
from ._serve_init import create
from ._serve_link import link

__all__ = ["register"]

DEFAULT_PORT = 2160
DEFAULT_ROOT = "~/taskops-server"

_HELP = "many projects' boards on one port, each behind a token"


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("serve", help=_HELP)
    _root(parser, inherit=False)
    parser.add_argument("--host", default="127.0.0.1",
                        help="bind address (default: loopback only)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--readonly", action="store_true",
                        help="refuse every write, on every project")
    parser.add_argument("--rate-limit", type=int, default=0, dest="rate_limit",
                        help="requests per minute, 0 for none")
    parser.add_argument("--no-create", action="store_true", dest="no_create",
                        help="refuse `taskops board create` — boards only from this box")
    parser.set_defaults(run=run)
    inner = parser.add_subparsers(dest="serve_command", metavar="<subcommand>")
    created = inner.add_parser("init", help="create a project here and mint its token")
    created.add_argument("project", help="its name and its URL segment: [a-z0-9-]")
    _root(created, inherit=True)
    created.set_defaults(run=run_init)
    linked = inner.add_parser("link", help="tie a project to a GitHub repo, so its "
                                           "collaborators can log in with `taskops login`")
    linked.add_argument("project")
    linked.add_argument("--github", metavar="owner/repo", default="",
                        help="the repository whose PUSH access grants the board")
    linked.add_argument("--remove", action="store_true", help="unlink; back to token only")
    _root(linked, inherit=True)
    linked.set_defaults(run=run_link)


def _root(parser: argparse.ArgumentParser, *, inherit: bool) -> None:
    """`--root` on BOTH parsers, so `serve init x --root /srv` reads as naturally as
    `serve --root /srv init x`. The subcommand's copy defaults to SUPPRESS, or argparse would
    write its default over the value the parent already parsed."""
    parser.add_argument("--root", default=argparse.SUPPRESS if inherit else DEFAULT_ROOT,
                        help=f"the directory of projects (default: {DEFAULT_ROOT})")


def run(args: argparse.Namespace) -> str:
    """Blocks until interrupted. The banner goes to stderr, like `taskops ui`'s."""
    root = Path(str(args.root)).expanduser().resolve()
    route = mount(root, readonly=bool(args.readonly), rate_limit=int(args.rate_limit),
                  create=not bool(getattr(args, "no_create", False)))
    server = serve_route(str(args.host), int(args.port), route)
    print(f"taskops serve → http://{args.host}:{bound_port(server)}/<project>/  ({root})"
          + ("  [read-only]" if args.readonly else "")
          + ("  [no remote create]" if getattr(args, "no_create", False) else ""),
          file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped", file=sys.stderr)
    finally:
        server.server_close()
    return ""


def run_init(args: argparse.Namespace) -> str:
    return create(Path(str(args.root)).expanduser().resolve(), str(args.project))


def run_link(args: argparse.Namespace) -> str:
    """Show, set or remove the GitHub repository that stands for this project's access list."""
    return link(Path(str(args.root)).expanduser().resolve(), str(args.project),
                slug=str(args.github), remove=bool(args.remove))
