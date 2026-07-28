"""`taskops remote` — where this project syncs, and the token that proves who it is.

With no subcommand it SHOWS, for the same reason `taskops tasks` lists: the thing you want
nine times out of ten should not cost a second turn. What it shows never includes the token —
it prints a length and nothing else, because the whole point of a terminal is that somebody
may be looking at it, and this is the one value in the system that a screenshot leaks.
"""

from __future__ import annotations

import argparse

from ....usecases import add_remote, read_remote, remove_remote
from ._shared import add_target, repo_of

__all__ = ["register"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("remote", help="show, set or drop the server this project syncs with")
    add_target(parser)
    parser.set_defaults(run=run_show, subcommand="")
    inner = parser.add_subparsers(dest="subcommand", metavar="<subcommand>")
    adding = inner.add_parser("add", help="register the one remote for this project")
    adding.add_argument("url", help="the server's base URL, e.g. https://taskops.example.com")
    adding.add_argument("--token", required=True, help="the bearer the server issued you")
    add_target(adding, inherit=True)
    adding.set_defaults(run=run_add)
    dropping = inner.add_parser("remove", help="forget the remote and its token")
    add_target(dropping, inherit=True)
    dropping.set_defaults(run=run_remove)


def run_show(args: argparse.Namespace) -> str:
    found = read_remote(repo_of(args))
    if found is None:
        return ("no remote — this project syncs through git (`taskops sync`). Add one with "
                "`taskops remote add <url> --token <token>`")
    return (f"{found['url']}\n  token   {_masked(found['token'])}\n"
            f"  cursor  seq {found['cursor']} of the server's log")


def run_add(args: argparse.Namespace) -> str:
    added = add_remote(repo_of(args), str(args.url), str(args.token))
    return (f"remote set to {added['url']} — the token is in .taskops/remote.json (mode 0600, "
            f"gitignored). `taskops push` to send this board up.")


def run_remove(args: argparse.Namespace) -> str:
    return f"remote {remove_remote(repo_of(args))} removed, token deleted"


def _masked(token: str) -> str:
    """Its LENGTH, never a prefix. A prefix is enough to recognise a token in a leaked log
    and enough to confirm a guess, and it answers no question worth answering."""
    return f"set ({len(token)} characters)" if token else "MISSING — the server will refuse"
