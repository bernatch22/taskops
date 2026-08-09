"""Credentials: revocable rows, not a string compared in a mount.

A token, an invite and a GitHub session are the SAME row with different
subjects. Only the sha256 is stored, comparison is `compare_digest`, and
revoking is an UPDATE — v1 could only rotate the board token, which threw
everybody out at once.

An invite is single use: redeeming it mints a personal credential and burns
the invite in the same transaction.
"""

from __future__ import annotations

import sqlite3
from typing import Any, NamedTuple
from hashlib import sha256
from pathlib import Path
from secrets import compare_digest

from .._ids import new_token
from .._errors import Refused, TaskopsError

DDL = """
CREATE TABLE IF NOT EXISTS credentials (
    id        TEXT PRIMARY KEY,
    hash      TEXT NOT NULL,
    subject   TEXT NOT NULL,   -- dev:ana | agent:… | machine:ci | invite:ana
    board     TEXT NOT NULL,   -- a board name, or '*'
    caps      TEXT NOT NULL,   -- comma separated: read,write,admin
    expires   REAL NOT NULL,   -- 0 means never
    revoked   INTEGER NOT NULL DEFAULT 0,
    once      INTEGER NOT NULL DEFAULT 0,
    created   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS credentials_hash ON credentials(hash);
"""

WEEK = 7 * 24 * 3600.0

EXPIRED = "that credential expired"
"""The refusal a run-out session wears, named so the CLIENT can recognise its own
case (`board.py`) instead of matching a sentence that would drift the first time
somebody reworded it. The words after it stay a human's instruction."""


class Credential(NamedTuple):
    id: str
    subject: str
    board: str
    caps: frozenset[str]
    once: bool


class Credentials:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.db = sqlite3.connect(path, check_same_thread=False)
            self.db.executescript(DDL)
            self.db.commit()
        except sqlite3.Error as err:
            raise TaskopsError(f"cannot open credentials at {path}: {err}") from err

    def mint(
        self,
        subject: str,
        board: str,
        now: float,
        *,
        caps: str = "read,write",
        ttl: float = 0.0,
        once: bool = False,
    ) -> tuple[str, Credential]:
        """Returns the plaintext ONCE. Only its digest is kept."""
        token = new_token()
        ident = sha256(f"{subject}{board}{now}{token}".encode()).hexdigest()[:16]
        self._write(
            "INSERT INTO credentials (id, hash, subject, board, caps, expires, once, created)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ident,
                _digest(token),
                subject,
                board,
                caps,
                now + ttl if ttl else 0.0,
                int(once),
                now,
            ),
        )
        return token, Credential(ident, subject, board, frozenset(caps.split(",")), once)

    def check(self, token: str, board: str, need: str, now: float) -> Credential:
        """Refuse with a reason a human can act on. Never leak which part failed."""
        rows = self._query(
            "SELECT id, hash, subject, board, caps, expires, revoked, once FROM credentials"
            " WHERE hash = ?",
            (_digest(token),),
        )
        for ident, digest, subject, scope, caps, expires, revoked, once in rows:
            if not compare_digest(str(digest), _digest(token)):
                continue
            if revoked:
                raise Refused("that credential was revoked — ask for a new invite")
            if expires and float(expires) < now:
                raise Refused(f"{EXPIRED} — ask for a new invite")
            if str(scope) not in ("*", board):
                raise Refused(f"that credential is not for board {board!r}")
            grants = frozenset(str(caps).split(","))
            if need not in grants:
                raise Refused(f"that credential may {', '.join(sorted(grants))} — not {need}")
            return Credential(str(ident), str(subject), str(scope), grants, bool(once))
        raise Refused("unknown credential — run: taskops join <url with ?token= or ?invite=>")

    def redeem(self, token: str, board: str, who: str, now: float) -> str:
        """Burn a single-use invite, mint a personal credential in its place."""
        invite = self.check(token, board, "read", now)
        if not invite.once:
            raise Refused("that is a standing credential, not an invite — use it as it is")
        self.revoke(invite.id)
        fresh, _ = self.mint(f"dev:{who}", board, now, caps="read,write")
        return fresh

    def revoke(self, ident: str) -> None:
        self._write("UPDATE credentials SET revoked = 1 WHERE id = ?", (ident,))

    def subject_of(self, ident: str) -> str:
        """Who a credential id belongs to — `""` when this host never minted it.

        `revoke` is an UPDATE and an UPDATE that matches nothing is a silent
        success, so a mistyped id would report "revoked" and leave the real
        credential live. The caller checks here first and refuses by name."""
        rows = self._query("SELECT subject FROM credentials WHERE id = ?", (ident,))
        return str(rows[0][0]) if rows else ""

    def boards(self, subject: str) -> set[str]:
        """The boards this subject holds a live credential for — which is what
        "a member sees their own boards" MEANS here, derived and never stored.
        `'*'` (a session, which is every board or none) is not a board."""
        rows = self._query(
            "SELECT DISTINCT board FROM credentials WHERE subject = ? AND revoked = 0",
            (subject,),
        )
        return {str(board) for board, in rows if str(board) != "*"}

    def close(self) -> None:
        self.db.close()

    def _query(self, sql: str, args: tuple[Any, ...]) -> list[tuple[Any, ...]]:
        try:
            rows: list[tuple[Any, ...]] = self.db.execute(sql, args).fetchall()
        except sqlite3.Error as err:
            raise TaskopsError(f"credentials: {err}") from err
        return rows

    def _write(self, sql: str, args: tuple[Any, ...]) -> None:
        try:
            with self.db:
                self.db.execute(sql, args)
        except sqlite3.Error as err:
            raise TaskopsError(f"credentials: {err}") from err


def _digest(token: str) -> str:
    return sha256(token.encode()).hexdigest()
