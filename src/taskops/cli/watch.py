"""`taskops join <url>` with NO invite and NO token — the VIEWER's join.

Its own module and not four more lines in `commands.py`, and the seam is real:
`join` connects a repo to a board it may WRITE on, and every step it takes
exists to make that true — an invite is burned, a key is registered, a session
is cached, the git hooks are installed so a commit reaches the board. This
command does none of those. It is the other half of GitHub's model, on the
client side: anyone may watch, and watching mints nothing.

The board is ASKED rather than assumed public — one anonymous `board` read
through the same `RemoteBoard` everything else uses — so the answer is the
SERVER's, and a private board refuses in exactly the words it always has.

**Three things a normal join does are skipped, and every one of them is a
WRITE.** `gitwork/remote.py::remember` records this repo's origin as a project
event ON THE BOARD: the milestone's second rule (anonymous never causes a
write), broken by the very command meant to make you a reader. The two git
hooks are skipped one step later for the same reason — the commit hook binds a
sha to a card, so every commit in a viewer's clone would print a refusal it can
do nothing about. What IS written is local and only local: `board.json` (with
`readonly`, which is what tells `board.py::open_board` this is a window and not
a broken join) and the MCP entry, so the read tools and `taskops ui` open.
"""

from __future__ import annotations

import sys
from pathlib import Path

from ..board import RemoteBoard
from .._errors import TaskopsError
from ..gitwork import install, claudefiles
from ..core.types import ANON

NO_LINK = "that URL carries no ?token= or ?invite= — ask for a fresh link"

TIMEOUT = 20.0


def watch(root: Path, base: str) -> int:
    """Join a PUBLIC board as nobody. Refuses — in the board's own words — otherwise."""
    try:
        RemoteBoard(base, "", ANON, TIMEOUT).call("board", {})
    except TaskopsError as err:
        raise TaskopsError(f"{NO_LINK}. (Reading it as nobody was refused: {err})") from err
    install.write_config(root, base, "", readonly=True)
    install.write_gitignore(root)
    claudefiles.write_mcp(root, sys.executable, ANON)
    print(f"watching {base} — read only, as nobody. Nothing was minted and no key registered.")
    print("  to write on it, ask the owner for an invite: taskops join <url>?invite=… --key …")
    return 0
