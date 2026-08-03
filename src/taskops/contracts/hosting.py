"""What a SERVER hosts: the shape of a board's name, its secret, and the pointer to it.

Layer 1 rather than inside the HTTP transport, which is where two of these used to live, and
the move is what `board create` needed: provisioning a board is a USE CASE now — a client asks
for one over the wire — and a use case that imported a transport to learn what may name a
directory would be the architecture upside down.

Distinct from `contracts.board`, which is the COLUMN VIEW a person reads. This is the board as
a thing a server holds: a directory, a token, a GitHub link. Two meanings of one word, kept in
two files so neither has to qualify itself every time it is named.
"""

from __future__ import annotations

import re
from typing import TypedDict

__all__ = ["NAME", "TOKEN_FILE", "BOARD_FILE", "HostedBoard"]

NAME = re.compile(r"^[a-z0-9-]{1,40}$")
"""What may name a board. Deliberately narrower than "a valid directory name": lowercase,
digits and dashes only, so the name is also a URL segment nobody has to escape — and `..`,
`/`, an empty string and a leading dot are all refused by the pattern itself."""

TOKEN_FILE = "token"
"""The board's secret, `0600`. A board without one is not served AT ALL, rather than served
open: this transport faces the internet, and the failure mode of the alternative is a board
that is public because a file was missing."""

BOARD_FILE = "board.json"
"""`.taskops/board.json` — the board's ADDRESS, committed, holding no secret.

The `.git/config` of a board. A clone carries where its board lives, so `taskops join` needs no
URL pasted from a chat, exactly as `git clone` needs no remote configured afterwards. It is
safe to commit because it is a URL and nothing else: the credential is a session in the home
directory, and the machine token — when there is one — is in `remote.json`, which the ignore
block guards by name.
"""


class HostedBoard(TypedDict):
    """One board on a server, as the wire describes it."""

    name: str
    """Its URL segment, matching `NAME`."""

    github: str
    """`owner/repo` whose push access grants it, or "" for a token-only board."""
