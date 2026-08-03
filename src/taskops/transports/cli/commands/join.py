"""`taskops join` — everything between a clone and a working board, in one command.

The URL is OPTIONAL, and that is the whole ambition: a clone carries `.taskops/board.json`, so
the second developer types two words. Passing one is for the first person to join a board
nobody has committed the address of yet — and it writes that address for everybody after.
"""

from __future__ import annotations

import argparse

from ....usecases.join import join
from ._shared import add_target, repo_of

__all__ = ["register", "run"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("join", help="join this repo's board: init, wire the hooks and "
                                         "MCP, connect, and pull — no URL needed")
    parser.add_argument("url", nargs="?", default="",
                        help="the board's address, if this clone does not carry one yet: "
                             "https://server/project?token=…")
    add_target(parser)
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    done = join(repo_of(args), str(args.url or ""))
    lines = [f"joined {done.url}", f"  project: {done.root}"]
    if done.adopted:
        lines.append(f"  {done.adopted} event(s) adopted from the checkout")
    if done.hooks:
        lines.append(f"  git hooks: {', '.join(done.hooks)}")
    lines.append("login needed: run `taskops login " + done.url.rsplit("/", 1)[0] + "`"
                 if done.needs_login else
                 "you are on the board — `taskops attention` says what it is waiting on")
    return "\n".join(lines)
