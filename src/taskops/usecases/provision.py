"""Making one board on a server: the directory, the store, and the secret that is its door.

A USE CASE and no longer a CLI helper, because it now has two callers that must not drift: the
person typing `taskops serve init` on the box, and — the whole point of `board create` — an
HTTP request from somebody's laptop who never logs into it. Two implementations of "what a new
board is" would differ in exactly one thing at a time, and the one that mattered would be the
missing `0600`.

The token model is the one proven in `bgist`: minted BY THE BOX, into a `0600` file, printed
exactly once, never in git and never in a log. Nothing here can recover it — a lost token is
re-minted, not looked up — because a tool that can print a secret twice is a tool whose
transcript is a secret.
"""

from __future__ import annotations

import secrets
from pathlib import Path

from .._errors import BadRequest
from ..contracts.hosting import NAME, TOKEN_FILE
from .setup import init as setup

__all__ = ["provision", "exists", "TOKEN_BYTES"]

TOKEN_BYTES = 16
"""128 bits from `secrets`, hex-encoded. Long enough that the 404 on a wrong name is the only
enumeration surface, and short enough to paste."""


def provision(root: Path, name: str) -> str:
    """Make `<root>/<name>/`, init a store in it, mint the token. Returns the token, or "" when
    the board already had one — minted once and never reprinted.

    Idempotent except for that: re-running repairs a board's store and leaves its secret alone.
    """
    if not NAME.match(name):
        raise BadRequest(f"'{name}' cannot name a board — use [a-z0-9-], 1 to 40 characters, "
                         f"because the name is also a URL segment")
    home = root / name
    home.mkdir(parents=True, exist_ok=True)
    # No git hooks: a server directory is a store of boards, not a working tree, and there is
    # no repository here whose commits a hook could bind to.
    setup(home, install_git_hooks=False)
    return _mint(home / TOKEN_FILE)


def exists(root: Path, name: str) -> bool:
    """Whether that board is already there. Asked before creating so the refusal can name it
    rather than silently adopting somebody else's board as your own."""
    return bool(NAME.match(name)) and (root / name / TOKEN_FILE).is_file()


def _mint(path: Path) -> str:
    """Write the secret `0600`, or leave an existing one alone and return "".

    `touch(mode=0o600)` BEFORE the write, so the file never exists — not even for the
    microsecond between create and chmod — with the umask's permissions.
    """
    if path.is_file():
        return ""
    path.touch(mode=0o600)
    token = secrets.token_hex(TOKEN_BYTES)
    path.write_text(token + "\n", encoding="utf-8")
    return token
