"""`taskops guard commit` — the PreToolUse hook, and the exit code that denies.

Claude Code's hook protocol is the reason this command returns an int instead of text:

```
exit 0  -> allow. stdout is shown to the user, not to the model.
exit 2  -> DENY. stderr goes to the MODEL, which is how the agent learns the reason.
other   -> a non-blocking error; the tool call proceeds.
```

So a refusal must be written to STDERR with code 2, and anything else — including a crash
in taskops itself — must let the commit through. That last part is deliberate: a
coordination tool that blocks commits because its database was locked has broken the thing
it exists to support, and there is a `post-commit` hook that will record the commit anyway.
"""

from __future__ import annotations

import argparse
import sys

from ...._errors import TaskopsError
from ....render import render_verdict
from ....usecases import check_commit
from ._shared import add_target, repo_of

__all__ = ["register"]

DENY = 2
ALLOW = 0


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("guard", help="decide whether a commit may proceed (hook)")
    add_target(parser)
    parser.add_argument("what", choices=("commit",))
    parser.add_argument("--message", default="", help="the commit message being written")
    parser.add_argument("--actor", default="", help="who is calling")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> int:
    """The verdict, as an exit code. Prints the amended message on stdout when allowed.

    Every unexpected failure ALLOWS. Fail-open is the right default for a guard in the
    commit path: the cost of wrongly allowing one commit is a missing association that
    `post-commit` will usually add anyway, and the cost of wrongly blocking is a developer
    who cannot commit and a tool they will uninstall.
    """
    try:
        verdict = check_commit(repo_of(args), str(args.message), actor=str(args.actor))
    except (TaskopsError, OSError) as err:
        print(f"taskops guard could not run ({err}) — allowing the commit",
              file=sys.stderr)
        return ALLOW
    if not verdict.allowed:
        print(render_verdict(verdict), file=sys.stderr)
        return DENY
    if verdict.message and verdict.message != args.message:
        print(verdict.message)
    return ALLOW
