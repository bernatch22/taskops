"""An INVITE — one person, one board, one use.

The third way in, and the one for a board that has no GitHub repository behind it. The other
two are a project TOKEN (one string, shared, anonymous, and rotating it locks everybody out)
and a GitHub login (a real per-person identity, but only where the work lives on GitHub). An
invite is the per-person credential for everywhere else: the owner mints one naming who it is
for, the person redeems it once, and from then on they hold an ordinary session.

Four properties, each closing a way this shape usually leaks:

- **Single use.** A code that works twice is a code that works forever, because it is sitting
  in a chat log. Redeeming consumes it.
- **It expires**, on the session's own week. An invite nobody used is a door left open.
- **It NAMES the invitee**, so the board records `dev:ana` rather than "somebody who had the
  link" — which is the whole reason not to just share the token.
- **Stored hashed.** The server keeps a digest, never the code. A leaked `invites.json` is then
  a list of names, not a set of working keys, and the code exists in exactly one place: the
  message the owner sent.
"""

from __future__ import annotations

from typing import TypedDict

__all__ = ["Invite", "INVITE_FILE", "INVITE_TTL"]

INVITE_FILE = "invites.json"
"""Beside the board's `token` and `github`, `0600`. Per board on purpose: an invite is to ONE
board, so a server-wide file would be a place to get that wrong."""

INVITE_TTL = 7 * 24 * 3600.0
"""A week — the session's own lifetime, deliberately the same number. Two different windows
would be two things to reason about, and nobody can say which one bit them."""


class Invite(TypedDict):
    """One pending invitation, as the server keeps it."""

    who: str
    """The bare name it was minted for — `ana`. Becomes `dev:ana` when redeemed."""

    digest: str
    """`sha256` of the code. The code itself is never stored, never logged, never reprinted."""

    by: str
    """Who minted it, for the sentence somebody reads three weeks later."""

    created: float
