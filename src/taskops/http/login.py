"""The two doors that MINT a credential: `POST /login` and `POST /<b>/invite/redeem`.

    POST /login  {"principal": "berna"}
      -> {"nonce": …, "expires": …, "namespace": "taskops"}
    POST /login  {"principal": "berna", "nonce": …, "signature": "-----BEGIN SSH…"}
      -> {"token": …, "expires": …, "actor": "dev:berna", "role": "owner"}

A KEY AUTHENTICATES A LOGIN; the login mints a short-lived SESSION TOKEN
through `store/creds.py`, which already existed. Every downstream path — /rpc's
bearer check, /feed, the MCP board — is UNTOUCHED, and that is the whole reason
the design was chosen over signing every request: a per-request envelope would
have to be taught to the stdlib HTTP server, to the WebSocket handshake and to
the MCP layer, three times, each a place to get it subtly wrong. Here exactly
one thing changed: where tokens COME FROM. They stop being a string a human
copies out of a terminal and become an artifact a key mints.

`register()` below is the shared effect of every enrolment: the invite door
above burns a link for it, and `members.enroll` — the OWNER's batch, filled
from GitHub by `cli/team.py` — reaches the same function from the other side.
GitHub had a door of its own beside these for a day — a stranger's own token in
a body, verified against the repo — and it is gone: the owner already knows who
works on the repo, so nobody has to prove it at this host's door. Whatever
enrolled a key, what the holder does next is the ordinary `/login` above.

The legacy flow is untouched and stays legacy on purpose (milestone rule 3:
production has four boards with minted bearer tokens). `invite/redeem` answers
exactly what it always did; a `pubkey` in the same body is the NEW half — the
invite is burned and the key registered in one call, so the joiner's next
session is keyed and no token is ever copied again.
"""

from __future__ import annotations

from typing import Any
from pathlib import Path
from threading import Lock

from ..core import scope
from .._errors import Refused, NotFound, BadRequest
from ..gitwork import sig
from ..store.creds import Credentials
from ..store.server import SERVER_DB, ServerStore
from ..core.challenge import Challenges

SESSION_TTL = 12 * 3600.0
"""A working day. Long enough that the transparent refresh in `board.py` runs
twice a day rather than per call, short enough that a leaked token is a
today-problem — which is the trade the whole chapter is for."""

NO_OWNER = (
    "this host has no owner yet, so it can verify nobody — the machine's own shell is "
    "where that starts: taskops server init --root <dir> --key ~/.ssh/id_ed25519.pub"
)


class Host:
    """The SERVER's own identity, opened only when somebody actually asks it.

    LAZY, and that is a rule and not a micro-optimisation: `ServerStore` makes
    its root and rewrites `allowed_signers` on construction, so building one
    eagerly would mean an anonymous request to a host nobody bootstrapped left
    files behind — the milestone's second rule (ANONYMOUS NEVER CAUSES A WRITE)
    and exactly the bug `mounts.py::stores` carries the post-mortem for.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.challenges = Challenges()
        self._lock = Lock()
        self._store: ServerStore | None = None

    @property
    def bootstrapped(self) -> bool:
        return (self.root / SERVER_DB).is_file()

    def store(self) -> ServerStore:
        if not self.bootstrapped:
            raise NotFound(NO_OWNER)
        with self._lock:
            if self._store is None:
                self._store = ServerStore(self.root)
            return self._store

    def close(self) -> None:
        with self._lock:
            if self._store is not None:
                self._store.close()
                self._store = None


def answer(
    host: Host,
    creds: Credentials,
    door: str,
    board: str,
    body: dict[str, Any],
    now: float,
) -> dict[str, Any]:
    """One entry point for both minting doors — the router stays a router."""
    return _login(host, creds, body, now) if door == "login" else _redeem(host, creds, board, body, now)


def _login(host: Host, creds: Credentials, body: dict[str, Any], now: float) -> dict[str, Any]:
    principal = str(body.get("principal", "")).strip()
    if not principal:
        raise BadRequest('POST {"principal": "<your name on this host>"} to start a login')
    store = host.store()
    # The gate is `core/scope.py`'s, not a second copy of the rule: an
    # unregistered principal is `anon`, and anon may not mint a session — the
    # refusal it raises names how a key gets registered.
    scope.permit("session.mint", store.role_of(principal))
    if not body.get("signature"):
        made = host.challenges.issue(principal, now)
        return {
            "nonce": made.nonce,
            "expires": made.expires,
            "namespace": sig.NAMESPACE,
        }
    held = host.challenges.claim(str(body.get("nonce", "")), now)
    if held.principal != principal:
        raise Refused(f"that challenge was issued to {held.principal!r}, not {principal!r}")
    sig.verify(store.signers, principal, held.payload, str(body.get("signature", "")))
    role = store.role_of(principal)
    caps = "read,write,admin" if role == scope.ROLE_OWNER else "read,write"
    token, _ = creds.mint(f"dev:{principal}", "*", now, caps=caps, ttl=SESSION_TTL)
    return {
        "token": token,
        "expires": now + SESSION_TTL,
        "actor": f"dev:{principal}",
        "principal": principal,
        "role": role,
    }


def _redeem(
    host: Host, creds: Credentials, board: str, body: dict[str, Any], now: float
) -> dict[str, Any]:
    who = str(body.get("who", "")).strip()
    token = str(body.get("invite", "")).strip()
    if not who or not token:
        raise BadRequest('POST {"invite": "…", "who": "<your name>"}')
    fresh = creds.redeem(token, board, who, now)
    out: dict[str, Any] = {"token": fresh, "actor": f"dev:{who}"}
    if str(body.get("pubkey", "")).strip():
        out["principal"] = register(host, who, str(body["pubkey"]), now)
    return out


def register(host: Host, who: str, keyline: str, now: float) -> str:
    """Register the joiner's key — AFTER the invite was burned, so an unredeemed
    body can never enrol anybody.

    THE enrolment, shared rather than copied: `members.py` calls it too, once
    per person in the owner's batch, so there is one description of what joining
    does to this host's store and one place where that description can change.
    What differs between the doors is the PROOF that precedes it — a burned
    invite here, the owner's own authority there — never the effect.

    `enroll` is not called blindly: it is an INSERT OR REPLACE on `principals`,
    so calling it for a name this host already knows would silently rewrite that
    principal's role — an owner who re-joins with an invite would demote itself.
    A known principal only ever gains a KEY here.
    """
    store = host.store()
    if store.principal(who) is None:
        store.enroll(who, scope.ROLE_MEMBER, keyline, now)
    else:
        store.add_key(who, keyline, now)
    return who
