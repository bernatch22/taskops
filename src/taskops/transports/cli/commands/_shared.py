"""What every command's parser repeats. One place, so the flags cannot drift.

`--repo` defaults to the cwd because the callers are hooks: git runs them from inside the
repository, and Claude Code runs them from the project directory, so requiring the path
would make every hook line longer for no information.
"""

from __future__ import annotations

import argparse
from pathlib import Path

__all__ = ["add_target", "add_actor", "add_identity", "repo_of"]


def add_target(parser: argparse.ArgumentParser, *, inherit: bool = False) -> None:
    parser.add_argument("--repo", default=_default(".", inherit),
                        help="path in the repository (default: the current directory)")


def add_actor(parser: argparse.ArgumentParser, *, inherit: bool = False) -> None:
    parser.add_argument("--actor", default=_default("", inherit),
                        help="who is calling: agent:<dev>/<name> or dev:<name>")


def _default(value: str, inherit: bool) -> object:
    """`SUPPRESS` when a PARENT parser already carries this flag.

    argparse writes a subparser's defaults into the namespace the parent already filled, so
    a group whose subcommands re-declare `--repo` would silently reset it: `taskops tasks
    --repo /x list` would look in the current directory instead. `SUPPRESS` is the only way
    to say "set nothing when it was not given", which leaves the parent's value standing.
    """
    return argparse.SUPPRESS if inherit else value


def add_identity(parser: argparse.ArgumentParser) -> None:
    """`--actor` and `--session`, for the callers that know who they are.

    Both optional: an actor resolves from $TASKOPS_ACTOR or git, and a session id only
    exists when Claude Code passed one. A hook that has them should say so, because that is
    what links the work to a transcript on the live board.
    """
    parser.add_argument("--actor", default="",
                        help="who is calling: agent:<dev>/<name> or dev:<name>")
    parser.add_argument("--session", default="", help="the Claude Code session id")


def repo_of(args: argparse.Namespace) -> Path:
    return Path(str(args.repo))
