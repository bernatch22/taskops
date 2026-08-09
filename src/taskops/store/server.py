"""The SERVER's own identity: who owns this host, and which keys speak for them.

    <root>/server.sqlite     the truth — principals and their pubkeys
    <root>/allowed_signers   DERIVED — what `ssh-keygen -Y verify` consumes

The relationship between them is `cache.sqlite`'s to `events.jsonl`: the store
is the truth, the file a projection regenerated from it on every change. Delete
`allowed_signers` and the next write puts it back; hand-edit it and the next
write overwrites the edit. Nothing ever reads a key OUT of the file into the
store — that direction is what made v1's `authorized_keys` drift into the only
record of who had access.

A SERVER-scope store, not a board's. `store/creds.py` (bearer tokens, per
board, in that board's `live.sqlite`) is untouched and keeps working: keys are
how tokens come to be MINTED, never a replacement that strands a fleet.

**Why ssh at all, exactly once.** Trust has to enter through a channel that
predates the system. `taskops server init` is that channel and it is the
machine's own shell: the human who can already log in says "this pubkey is the
owner", and from then on every admin act is a signed call over the API. A
remote bootstrap would need a credential to authorise it and there is none yet
— that regress is what ssh cuts, and it is the ONLY ssh in this design.

No pip dependency and no hand-rolled crypto: the fingerprint is OpenSSH's own
`SHA256:<base64>` over the blob the key line already carries, and the signing
itself is `ssh-keygen -Y sign/verify`.
"""

from __future__ import annotations

import sqlite3
from typing import Any, NamedTuple
from pathlib import Path

from .pubkeys import parse_key, fingerprint, principal_name
from .._errors import Refused, BadRequest, TaskopsError
from ..core.scope import ROLE_ANON, ROLE_OWNER, ROLE_MEMBER, SERVER_ROLES

SERVER_DB = "server.sqlite"
SIGNERS = "allowed_signers"

DDL = """
CREATE TABLE IF NOT EXISTS principals (
    name    TEXT PRIMARY KEY,
    role    TEXT NOT NULL,          -- owner | member
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS pubkeys (
    fingerprint TEXT PRIMARY KEY,   -- SHA256:… exactly as ssh-keygen -l prints it
    principal   TEXT NOT NULL,
    keyline     TEXT NOT NULL,      -- "<type> <base64>", the comment stripped
    created     REAL NOT NULL,
    revoked     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS pubkeys_principal ON pubkeys(principal);
"""


class Principal(NamedTuple):
    name: str
    role: str


class Key(NamedTuple):
    fingerprint: str
    principal: str
    keyline: str
    revoked: bool


class ServerStore:
    """Principals, their keys, and the `allowed_signers` file derived from both."""

    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self.signers = root / SIGNERS
        try:
            self.db = sqlite3.connect(root / SERVER_DB, check_same_thread=False)
            self.db.executescript(DDL)
            self.db.commit()
        except sqlite3.Error as err:
            raise TaskopsError(f"cannot open the server store at {root}: {err}") from err
        self._regenerate()

    # ── principals ──────────────────────────────────────────────────────────

    def enroll(self, name: str, role: str, keyline: str, now: float) -> Key:
        """Record a principal AND its first key. The bootstrap, and every join."""
        if role not in (ROLE_OWNER, ROLE_MEMBER):
            raise BadRequest(f"role {role!r} — a principal is {ROLE_OWNER} or {ROLE_MEMBER}")
        if role == ROLE_OWNER and (held := self.owner()) is not None and held.name != name:
            raise Refused(
                f"this server is already owned by {held.name!r} — "
                f"register {name!r} as a member instead"
            )
        self._write(
            "INSERT OR REPLACE INTO principals (name, role, created) VALUES (?, ?, ?)",
            (principal_name(name), role, now),
        )
        return self.add_key(name, keyline, now)

    def principal(self, name: str) -> Principal | None:
        rows = self._query("SELECT name, role FROM principals WHERE name = ?", (name,))
        return Principal(str(rows[0][0]), str(rows[0][1])) if rows else None

    def principals(self) -> list[Principal]:
        rows = self._query("SELECT name, role FROM principals ORDER BY name", ())
        return [Principal(str(name), str(role)) for name, role in rows]

    def owner(self) -> Principal | None:
        rows = self._query(
            "SELECT name, role FROM principals WHERE role = ? ORDER BY created LIMIT 1",
            (ROLE_OWNER,),
        )
        return Principal(str(rows[0][0]), str(rows[0][1])) if rows else None

    def role_of(self, name: str) -> str:
        """The SERVER role of a principal — `anon` for anyone this host has never
        been told about. Never raises: not being registered is an answer."""
        found = self.principal(name)
        return found.role if found and found.role in SERVER_ROLES else ROLE_ANON

    # ── keys ────────────────────────────────────────────────────────────────

    def add_key(self, principal: str, keyline: str, now: float) -> Key:
        if self.principal(principal) is None:
            raise Refused(
                f"no principal named {principal!r} on this server — "
                "the owner registers one before it can carry a key"
            )
        kind, blob = parse_key(keyline)
        key = Key(fingerprint(blob), principal, f"{kind} {blob}", False)
        self._write(
            "INSERT OR REPLACE INTO pubkeys (fingerprint, principal, keyline, created, revoked)"
            " VALUES (?, ?, ?, ?, 0)",
            (key.fingerprint, principal, key.keyline, now),
        )
        self._regenerate()
        return key

    def revoke_key(self, fingerprint_: str) -> None:
        self._write("UPDATE pubkeys SET revoked = 1 WHERE fingerprint = ?", (fingerprint_,))
        self._regenerate()

    def keys(self, principal: str = "", *, live: bool = True) -> list[Key]:
        sql = "SELECT fingerprint, principal, keyline, revoked FROM pubkeys WHERE 1 = 1"
        args: list[Any] = []
        if principal:
            sql += " AND principal = ?"
            args.append(principal)
        if live:
            sql += " AND revoked = 0"
        rows = self._query(sql + " ORDER BY principal, fingerprint", tuple(args))
        return [Key(str(f), str(p), str(k), bool(r)) for f, p, k, r in rows]

    def close(self) -> None:
        self.db.close()

    # ── the derived file ────────────────────────────────────────────────────

    def _regenerate(self) -> None:
        """Rewrite `allowed_signers` from the store, whole. Never appended to."""
        lines = [f"{key.principal} {key.keyline}" for key in self.keys()]
        body = "\n".join(lines) + ("\n" if lines else "")
        try:
            self.signers.write_text(body, encoding="utf-8")
        except OSError as err:
            raise TaskopsError(f"cannot write {self.signers}: {err}") from err

    # ── plumbing ────────────────────────────────────────────────────────────

    def _query(self, sql: str, args: tuple[Any, ...]) -> list[tuple[Any, ...]]:
        try:
            rows: list[tuple[Any, ...]] = self.db.execute(sql, args).fetchall()
        except sqlite3.Error as err:
            raise TaskopsError(f"server store: {err}") from err
        return rows

    def _write(self, sql: str, args: tuple[Any, ...]) -> None:
        try:
            with self.db:
                self.db.execute(sql, args)
        except sqlite3.Error as err:
            raise TaskopsError(f"server store: {err}") from err
