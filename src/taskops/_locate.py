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

import os
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


def write_remote(root: Path, fields: dict[str, Any]) -> None:
    """Merge `fields` into remote.json, keeping every other key it holds, 0600.

    The WRITER of the secret half, beside its reader, because the shape of that
    file is one fact: a session refresh (`session.remember`), the key that minted
    it (`session.cache_login`) and the host and board this checkout operates
    (`cli/remote.py`) each write ONE block and must not eat the others'.

    `login` is therefore MERGED FIELD BY FIELD and never replaced whole. Three
    writers own three fields of it — `remote add` the host, a sign-in the
    principal and the key, `board create` the board's name — and a plain
    top-level update would have the sign-in silently drop the recorded name, so
    the bare `board push` after it would go back to guessing the directory."""
    path = root / DIR / "remote.json"
    body: dict[str, Any] = {}
    if path.exists():
        try:
            body = as_object(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            body = {}
    if "login" in fields:
        fields = {**fields, "login": {**as_object(body.get("login")), **as_object(fields["login"])}}
    body.update(fields)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
