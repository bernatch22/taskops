"""Where the board is, and what its config says. Nothing here opens one.

Split out of `board.py` along the seam that file's own history names: v1 kept
this as `storage/locate.py`, and the two questions really are separate — *which
directory is this project's* is answered from the filesystem alone, while *how
do I talk to its board* needs the stores, the verbs and the network.

Two files make a project, and only `init`/`join` ever write them:

    .taskops/board.json    {"url": …}   committed — the address travels with the code
    .taskops/remote.json   {"token", "token_expires", "login"}   0600, gitignored —
                           the secret never travels, and with a `login` block the
                           token is a SESSION this machine re-mints (`session.py`)
"""

from __future__ import annotations

import json
from typing import Any
from pathlib import Path

from ._json import as_object

DIR = ".taskops"

# "A board lives here." Written by BOTH `init` and `join`, so it is the one
# marker every project has and nothing else creates.
ADDRESS = "board.json"


def is_project(candidate: Path) -> bool:
    """A directory is a project when `.taskops/board.json` is in it.

    The FILE, not the directory, and the distinction is not pedantry: v1 kept
    its sessions in `~/.taskops/`, so that directory exists on every machine
    that ever ran it — and matching the directory alone made the HOME DIRECTORY
    a project: `taskops init` in a fresh repo under it walked up, adopted HOME,
    and wrote the board, both git hooks, `.mcp.json` and the Claude settings
    there instead of in the repo. v1 hit and fixed this the same way
    (`storage/locate.py`); v2 shipped the bare check and reproduced it.
    """
    return (candidate / DIR / ADDRESS).is_file()


def find_root(start: Path) -> Path:
    """The nearest project, else the git root, else `start`.

    A project wins over `.git` deliberately: a worker's worktree lives at
    `<repo>/.taskops/trees/tk-…` and has a `.git` file of its own. Answering
    "the worktree" there would look for the credential in the wrong place and
    silently fall back to a local board — one of v1's split-brain routes. The
    walk finds `<repo>` anyway, because that is where the address file is.
    """
    here = start.resolve()
    chain = [here, *here.parents]
    for candidate in chain:
        if is_project(candidate):
            return candidate
    for candidate in chain:
        if (candidate / ".git").exists():
            return candidate
    return here


def read_config(root: Path) -> dict[str, Any]:
    """board.json (committed) merged with remote.json (secret). Missing is fine."""
    out: dict[str, Any] = {}
    for name in (ADDRESS, "remote.json"):
        path = root / DIR / name
        if not path.exists():
            continue
        try:
            data: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue  # a broken config means "not configured", never a crash on read
        out.update(as_object(data))
    return out
