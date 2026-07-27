"""What every command's parser repeats. One place, so the flags cannot drift.

`--repo` defaults to the cwd because the callers are hooks: git runs them from inside the
repository, and Claude Code runs them from the project directory, so requiring the path
would make every hook line longer for no information.
"""

from __future__ import annotations

import argparse
from pathlib import Path

__all__ = ["add_target", "add_identity", "repo_of"]


def add_target(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", default=".",
                        help="path in the repository (default: the current directory)")


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
