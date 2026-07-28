"""Creating one project on a server, and minting the secret that is its only door.

Split from `serve` because the two halves have nothing in common but a name: that one opens a
socket, this one writes two things to disk and prints a URL. Keeping them apart is also what
keeps the token handling in a file small enough to read in one sitting — which is the correct
size for the only code in taskops that mints a credential.

The model is the one that has already been proven in `bgist`: the token is minted BY THE BOX,
lands in a `0600` file, is printed exactly once, and never touches git or a log. Nothing here
can recover it — a lost token is re-minted, not looked up — because a tool that can print a
secret twice is a tool whose transcript is a secret.
"""

from __future__ import annotations

import secrets
from pathlib import Path

from ...._errors import TaskopsError
from ....transports.http.projects import NAME, TOKEN_FILE
from ....usecases import init as setup

__all__ = ["create"]

TOKEN_BYTES = 16
"""128 bits from `secrets`, hex-encoded. Long enough that the 404 on a wrong name is the only
enumeration surface, and short enough to paste."""


def create(root: Path, project: str) -> str:
    """Make `<root>/<project>/`, init a taskops store in it, mint the token. Idempotent
    EXCEPT for the token, which is minted once and never reprinted."""
    if not NAME.match(project):
        raise TaskopsError(f"'{project}' cannot name a project — use [a-z0-9-], "
                           f"1 to 40 characters, because the name is also a URL segment")
    home = root / project
    home.mkdir(parents=True, exist_ok=True)
    # No git hooks: a server directory is a store of boards, not a working tree, and there is
    # no repository here whose commits a hook could bind to.
    setup(home, install_git_hooks=False)
    token = _mint(home / TOKEN_FILE)
    return _describe(home, project, token)


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


def _describe(home: Path, project: str, token: str) -> str:
    if not token:
        return (f"{project} already exists at {home}\n"
                f"its token is in {home / TOKEN_FILE} — it is never printed twice")
    return (f"created {project} at {home}\n"
            f"token (shown ONCE, kept in {home / TOKEN_FILE}):\n\n    {token}\n\n"
            f"open the board at  http://<host>/{project}/?token={token}")
