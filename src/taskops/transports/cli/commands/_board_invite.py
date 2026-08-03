"""`taskops board invite` — the per-person way into a board with no GitHub behind it.

Its own module because it authorises differently from every other `board` verb, and that
difference is the design rather than an accident: `list`, `view` and `access` need a SERVER
session, because they ask the server about you. Inviting needs the BOARD's own credential — the
right to invite somebody is the right to write, and that is already sitting in `remote.json`.

Reading it from there is also what makes this work on a board with no GitHub link at all, which
is the whole case it exists for. A board that has one does not need invites: push access to the
repository already is one, and it revokes when the repository does.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ...._errors import BadRequest, TaskopsError
from ....usecases import read_remote
from ....usecases._routing import whoami
from ....usecases._sessionfile import bearer_of
from ....usecases.boards import invite_to, withdraw_invite

__all__ = ["run_invite"]


def run_invite(args: argparse.Namespace, root: Path) -> str:
    found = read_remote(root)
    if found is None:
        raise _no_board()
    who, credential = str(args.who).strip(), bearer_of(found["token"])
    if args.withdraw:
        gone = withdraw_invite(found["url"], credential, who)
        return (f"withdrew the invite for {who}" if gone.get("was_pending")
                else f"{who} had no pending invite")
    by = whoami(root, "")
    return _invited(found["url"], who, invite_to(found["url"], credential, who, by))


def _invited(board_url: str, who: str, answer: dict[str, Any]) -> str:
    """The receipt, and the ONE time the code is legible anywhere.

    It prints the whole COMMAND rather than the code, because a code alone is a thing the reader
    has to assemble a URL around, and assembling it by hand is the step this surface exists to
    delete. `join` already does init, the git hooks, the MCP wiring and the first pull — so the
    person invited runs one line and is working.
    """
    code = str(answer.get("code", ""))
    others = [name for name in answer.get("pending", []) if name != who]
    lines = [
        f"invited {who} to {board_url}",
        "",
        "  send them this — it works ONCE, and expires in 7 days:",
        f"      taskops join {board_url}?invite={code}",
        "",
        f"  the board will record them as `dev:{who}`. The code is stored only as a digest and",
        "  is never printed twice; inviting them again replaces it.",
    ]
    if others:
        lines += ["", f"  still pending: {', '.join(sorted(others))}"]
    return "\n".join(lines)


def _no_board() -> TaskopsError:
    return BadRequest("this project has no board yet — `taskops board create` makes one, or "
                      "`taskops join <url>` if somebody else already did")
