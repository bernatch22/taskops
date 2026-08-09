"""The nonce a login signs: server-issued, single-use, and gone on use.

WHY A CHALLENGE AND NOT A CLIENT TIMESTAMP. The obvious design — the client
signs "berna at 17:04:11" and the server accepts it inside a window — buys a
clock-skew parameter nobody can pick, and a replay cache that has to be sized
and expired. A nonce the SERVER issued needs neither: it exists because this
host made it, it is claimed exactly once, and claiming it removes it. There is
no window to widen and no cache to grow.

WHY MEMORY AND NOT A TABLE. A challenge outliving the process that issued it
would be a stored fact whose only job is to be contradicted seconds later —
`recover`'s shape (ARCHITECTURE.md §11). A restarted server simply has no
outstanding challenges, and the client asks for another one; that is the
correct behaviour, not a loss.

Pure by the layer's rule: no clock of its own (`now` arrives as an argument),
no file, no SQL. `Challenges` is mutable state, which a level-1 module may hold
— what it may not do is REACH for anything, and it does not.
"""

from __future__ import annotations

from typing import NamedTuple
from threading import Lock

from .._ids import new_token
from .._errors import Refused

TTL = 120.0
"""Two minutes. The client signs the moment it is answered, so this covers a
slow link and a slow disk, not a human; and it is the only lifetime that has to
be picked because there is no clock skew in the design."""

MAX_OUTSTANDING = 512
"""A ceiling, so an anonymous caller cannot grow this dict without end. Expired
entries go first; only if they were all live does the OLDEST live one go, which
costs its owner one retry and costs this host nothing."""

PURPOSE = "taskops-login"


def payload(principal: str, nonce: str) -> str:
    """The exact bytes both sides sign. A pure function on purpose: the client
    and the server compute it from the same code, so it cannot drift into two
    nearly-identical strings that fail with 'incorrect signature'."""
    return f"{PURPOSE}\n{principal}\n{nonce}\n"


class Challenge(NamedTuple):
    nonce: str
    principal: str
    expires: float

    @property
    def payload(self) -> str:
        return payload(self.principal, self.nonce)


class Challenges:
    """Outstanding nonces, by nonce. Thread-safe: the HTTP server is threading."""

    def __init__(self, ttl: float = TTL) -> None:
        self.ttl = ttl
        self._lock = Lock()
        self._open: dict[str, Challenge] = {}

    def issue(self, principal: str, now: float) -> Challenge:
        made = Challenge(new_token(), principal, now + self.ttl)
        with self._lock:
            self._prune(now)
            self._open[made.nonce] = made
        return made

    def claim(self, nonce: str, now: float) -> Challenge:
        """Take it, once. A second `claim` of the same nonce is a stranger's."""
        with self._lock:
            held = self._open.pop(nonce, None)
        if held is None:
            raise Refused(
                "that login challenge is unknown or already used — ask for a new one "
                "(a challenge is single-use by design); retry the login"
            )
        if held.expires < now:
            raise Refused(
                f"that login challenge expired ({self.ttl:.0f}s to sign it) — retry the login"
            )
        return held

    def count(self) -> int:
        with self._lock:
            return len(self._open)

    def _prune(self, now: float) -> None:
        for nonce, held in list(self._open.items()):
            if held.expires < now:
                del self._open[nonce]
        while len(self._open) >= MAX_OUTSTANDING:
            self._open.pop(next(iter(self._open)))
