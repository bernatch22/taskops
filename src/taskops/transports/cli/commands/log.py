"""Read what the agent said while working on a card — reached as `taskops tasks log`.

The top-level `taskops log` was one of the agent's, and the agent reads a card over MCP. The
function is untouched: `tasks log` points straight at it.
"""

from __future__ import annotations

import argparse

from ....render import render_log
from ....usecases import session_log
from ._shared import repo_of

__all__ = ["run"]


def run(args: argparse.Namespace) -> str:
    from ....usecases.log import MAX_ENTRIES

    return render_log(session_log(repo_of(args), str(args.task),
                                  limit=int(args.limit) or MAX_ENTRIES))
