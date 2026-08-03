"""The CLI: parse, dispatch, and translate a failure into an exit code.

The commands hold no argparse beyond their own flags and no decision beyond which renderer
to use. That is what lets the same behaviour be reached from MCP without a second
implementation, and it keeps this file about the terminal.

Exit codes: 0 fine, 1 an engine failure, 2 bad usage. Nothing here means anything else — the
one command that used an exit code as an ANSWER was `guard`, and it left with the rest of the
wiring for `transports/hooks`, where the caller is a hook rather than a person.
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from ..._errors import TaskopsError
from ..._version import __version__
from .commands import (
    attention,
    board,
    context,
    init,
    join,
    land,
    login,
    me,
    milestone,
    open_,
    policy,
    publish,
    pushpull,
    recover,
    remote,
    report,
    schedule,
    serve,
    setup,
    status,
    statusline,
    sync,
    tasks,
    ui,
)

__all__ = ["main", "build_parser"]

_COMMANDS = (init, join, board, setup, ui, serve, tasks, attention, milestone, context, me,
             policy, status,
             statusline, report, schedule, recover, sync, login, open_, publish, land, remote,
             pushpull)
"""Every command there is. Twenty-five, and `--help` lists all twenty-five.

`milestone`, `context` and `me` are three nouns over one log, split by WHOSE fact it is and how
long it lives: a chapter the board is in, what the project settled, and what one person is
chasing. They were two commands with a `--mine` flag, and the flag meant "file it under me" on a
write and "show my page" on a read — one word for two things nobody could keep straight.

`statusline` is the odd one and belongs here anyway: it is not for a person to type, it is what
`settings.json` runs to paint the bottom row of a Claude Code session. It sits beside `status`
because it is the same question at a different cadence — `status` when you ask, `statusline`
without being asked — and putting it anywhere else would have hidden it from the one person
looking for it, who is reading `--help` to find out what to put in that setting.

`policy` sits beside `context` because they are the two halves of "what this project has
already decided" — and apart from it because one is prose a worker weighs and the other is a
value the engine obeys. Folding the second into the first is what made a typo silent.

`login` sits with them because it is the first thing a new teammate types and the last thing
they should have to look for. It is the only command here that touches nothing under
`.taskops/`: a session belongs to the PERSON on this machine, so it goes to the home
directory and serves every checkout at once — which is why it takes no `--repo`.

`open` is `login`'s other half. Signing in produced a session that could reach several boards
and no way to visit one: the host was in the project, the credential was in the home directory,
and joining them was left to the reader. It is one word because it is the thing people do most.

`serve` sits next to `ui` because it is the same transport with a different audience: `ui`
serves the repository you are standing in, `serve` serves a directory of them over the network,
each behind its own token.

`remote`, `push` and `pull` are the developer's, which is why they are here and NOT on the
MCP surface: an agent works a board, it does not decide when this machine talks to a server.
They sit beside `sync` rather than replacing it — a team with no server converges through git
exactly as before, and that path is not deprecated by this one.

There used to be thirteen more, registered and hidden — the agent protocol (`next`, `update`,
`ask`, `plan`, `dispatch`, `log`) and the wiring (`guard`, `hook`, `ingest`, `brief`, `inbox`,
`track`, `checkout`). Hiding them made the help page honest and left the door open: git and
Claude Code still came in through the developer's binary. The agent's door is `taskops.mcp`
and the wiring's is `python -m taskops.transports.hooks`, so these are gone rather than
hidden, and the machinery that hid them went with them.

`run` is GONE, and with it the last way a person could start detached Claude processes from this
binary. It spawned one `claude -p` per card with a generic prompt and whatever model the shell
defaulted to — so a project's own specialist, its model and its tools never reached the worker
that was supposed to be it. The orchestration belongs inside a session, where the registry is
readable and sub-agents cost what the subscription already paid for: `taskops_dispatch` hands
back the briefs and the session spawns them."""


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
    if output:
        print(output)
    return 0


if __name__ == "__main__":       # `python -m taskops.transports.cli.main`
    raise SystemExit(main())
