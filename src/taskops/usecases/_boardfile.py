"""`.taskops/board.json` — where this repository's board lives, committed, and no secret in it.

The `.git/config` of a board, and it exists for one sentence: `taskops join` with no arguments.
Before it, the second developer needed a URL pasted from a chat — which is the step `git clone`
famously does not have, because a clone carries its own remote.

**Committed on purpose, and safe because there is nothing in it.** The ignore block lists paths
rather than ignoring `.taskops/` wholesale, so a new file there is tracked by default — which
was a hazard the day `remote.json` arrived holding a bearer, and is exactly right here. The
credential is a session in the home directory; the machine token, when there is one, stays in
`remote.json`, which the block guards by name.

Separate from `remote.json` for that reason alone: same idea, opposite disposition. One is the
address and travels with the repository; the other is the secret and must never leave the disk.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..contracts.hosting import BOARD_FILE
from ..storage import PROJECT_DIR

__all__ = ["read_pointer", "write_pointer", "pointer_path"]


def pointer_path(root: Path) -> Path:
    return root / PROJECT_DIR / BOARD_FILE


def read_pointer(root: Path) -> str:
    """The board's URL, or "" when this repository does not carry one.

    Unreadable and malformed both answer "" rather than raising: this file arrives through
    `git pull` from however many taskops versions a team runs, and a board nobody can join is
    a better failure than a command that cannot start.
    """
    try:
        found = json.loads(pointer_path(root).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return str(found.get("url", "")).strip() if isinstance(found, dict) else ""


def write_pointer(root: Path, url: str) -> Path:
    """Record the address, creating `.taskops/` if this is a fresh checkout.

    Ordinary permissions and an ordinary write: it is meant to be read by everybody who clones
    the repository, so the `0600`-and-atomic care `remote.json` takes would be cargo here.
    """
    path = pointer_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"url": url.strip().rstrip("/")}, indent=2) + "\n",
                    encoding="utf-8")
    return path
