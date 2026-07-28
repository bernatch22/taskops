"""`python -m taskops.transports.hooks <event>` — the executable the wiring names.

Seven flat subcommands, one per thing that can fire:

```
pre-tool-use  post-tool-use  session-start  stop     Claude Code, JSON on stdin
commit                                               Claude Code, exit 2 = DENY
ingest commit|branch          sync                   git: post-commit, post-checkout, post-merge
```

Flat, and named after the EVENT rather than the internal verb, because the reader of these
names is somebody staring at a `hooks.json` entry or a line in `.git/hooks/post-commit`.

Exit codes are the contract and they differ per subcommand, which is why `main` returns
whatever `run` returned instead of flattening it: `commit` answers 2 to deny, the Claude Code
events answer 0 always with the decision inside the JSON, and everything fails OPEN.
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from ..._errors import TaskopsError
from . import claude, commit, record

__all__ = ["main", "build_parser"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m taskops.transports.hooks",
        description="taskops wiring: the commands git and Claude Code run. Not for typing — "
                    "`taskops init` writes them into .git/hooks, and the plugin ships the rest.")
    sub = parser.add_subparsers(dest="event", required=True, metavar="<event>")
    for module in (claude, commit, record):
        module.register(sub)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one hook. A typed failure is ONE line on stderr, never a traceback.

    Code 1 for a failure the way the CLI does it, because git's line ends in `|| true` and
    Claude Code reads any non-zero-but-not-2 as a non-blocking error. The one code that means
    something is 2, and only `commit` returns it.
    """
    args = build_parser().parse_args(argv)
    try:
        output = args.run(args)
    except (TaskopsError, OSError) as err:
        print(f"taskops: {err}", file=sys.stderr)
        return 1
    if isinstance(output, int):
        return output
    if output:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
