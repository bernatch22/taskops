"""The CLI: parse, dispatch, and translate a failure into an exit code.

The commands hold no argparse beyond their own flags and no decision beyond which renderer
to use. That is what lets the same behaviour be reached from MCP without a second
implementation, and it keeps this file about the terminal.

Exit codes matter more here than in most CLIs, because the callers are git hooks and Claude
Code hooks rather than people: 0 fine, 1 an engine failure, 2 bad usage. The one special
case is `guard`, which uses 2 to mean DENY — see its module.
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from ..._errors import TaskopsError
from ..._version import __version__
from .commands import (
    ask,
    guard,
    hook,
    ingest,
    init,
    next_,
    plan,
    report,
    session,
    studio,
    sync,
    update,
)

__all__ = ["main", "build_parser"]

_COMMANDS = (init, next_, update, ask, plan, report, studio, guard, hook, ingest,
             session, sync)


def build_parser() -> argparse.ArgumentParser:
    """Every command registers its own flags. Adding one is a new module in `commands/`,
    never a branch here."""
    parser = argparse.ArgumentParser(
        prog="taskops",
        description="The shared task list for Claude Code agents: persistent tasks, "
                    "atomic claims, commits bound to the work that motivated them.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")
    for module in _COMMANDS:
        module.register(sub)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command. A typed failure prints ONE line naming what to do.

    A traceback is for the person who can fix the code; the reader here is trying to use the
    tool, or is a hook that will show the line to an agent.
    """
    args = build_parser().parse_args(argv)
    try:
        output = args.run(args)
    except (TaskopsError, OSError) as err:
        # OSError too: a path that does not exist or cannot be read is an ordinary mistake,
        # and the person who made it wants one line, not a traceback through pathlib.
        print(f"taskops: {err}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    if isinstance(output, int):
        return output           # `guard` decides its own code: 2 is a DENY, not an error
    if output:
        print(output)
    return 0


if __name__ == "__main__":       # `python -m taskops.transports.cli.main`
    raise SystemExit(main())
