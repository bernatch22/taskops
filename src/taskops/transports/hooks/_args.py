"""What every wiring subcommand's parser repeats.

`--repo` defaults to the cwd because the callers are hooks: git runs them from inside the
repository, and Claude Code runs them from the project directory, so requiring the path would
make every hook line longer for no information.

A copy of `cli/commands/_shared` rather than an import of it: a transport that imported
another transport would make the developer's CLI a dependency of git's wiring, which is the
coupling this whole module exists to remove. It is four lines, and they do not drift because
`test_hook_wiring` runs the real installed hook.
"""

from __future__ import annotations

import argparse
from pathlib import Path

__all__ = ["add_target", "repo_of"]


def add_target(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", default=".",
                        help="path in the repository (default: the current directory)")
    parser.add_argument("--actor", default="", help="who is calling")


def repo_of(args: argparse.Namespace) -> Path:
    return Path(str(args.repo))
