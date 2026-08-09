"""The CLIENT half of the ssh login: get a token, cache it, get another one later.

`remote.json` stops being a thing a human pastes into and becomes a SESSION
CACHE. Delete it and the next call mints a new session from the key; let it
expire and the same happens, with nobody watching — a human never copies a
token again, which is the whole promise of the chapter.

    .taskops/remote.json
    {
      "token": "…",                      the session, 0600, gitignored, disposable
      "token_expires": 1770043200.0,     when to stop trusting it
      "login": {"host": "https://…", "principal": "berna", "key": "~/.ssh/id_ed25519"}
    }

`login` is what makes the refresh possible; WITHOUT it this file does nothing at
all and the token in it is used exactly as it was before. That is milestone rule
3 — production has four boards on standing bearer tokens, and a config with no
`login` block is precisely one of those. A standing token (no `token_expires`)
is never replaced behind its owner's back either.

The failure policy is one sentence: **a working session beats a failed refresh.**
Host unreachable or ssh-keygen missing, but a token in hand: the call goes out
with it and the server decides. Only a client with no token at all turns a
failed login into the caller's error.

WHO signs in — key discovery, the principal, `establish` — is `identity.py`,
this file's caller-facing sibling; here lives only the token lifecycle."""

from __future__ import annotations

from typing import Any, Callable
from pathlib import Path

from . import _wire
from ._json import as_object
from ._errors import Unreachable, TaskopsError
from ._locate import write_remote
from .gitwork.sig import sign
from .core.challenge import payload

TIMEOUT = 20.0

SLACK = 300.0
"""Refresh five minutes EARLY. A session that expires between the check and the
call it authorises would be a bug that reproduces once a day at most, which is
the worst reproduction rate there is."""


def fresh(root: Path, config: dict[str, Any], now: float) -> str:
    """The token to use right now — refreshing it first if that is possible."""
    token = str(config.get("token", ""))
    door = as_object(config.get("login"))
    host, principal = str(door.get("host", "")), str(door.get("principal", ""))
    key = str(door.get("key", ""))
    if not (host and principal and key):
        return token  # a legacy join: the token in the file is the whole story
    expires = float(config.get("token_expires", 0.0) or 0.0)
    if token and (not expires or now + SLACK < expires):
        return token
    try:
        return sign_in(root, host, principal, Path(key).expanduser())
    except TaskopsError:
        if token:
            return token
        raise


def sign_in(
    root: Path, host: str, principal: str, key: Path, timeout: float = TIMEOUT, cache: bool = True
) -> str:
    """Challenge, sign, token — and write the session down. Two round trips.

    `cache=False` is the one case where it must NOT be written down: a session
    for a host this checkout is not joined to (`identity.is_own_host`)."""
    opened = _post(host, {"principal": principal}, timeout)
    nonce = str(opened.get("nonce", ""))
    signature = sign(payload(principal, nonce), key)
    minted = _post(host, {"principal": principal, "nonce": nonce, "signature": signature}, timeout)
    token = str(minted.get("token", ""))
    if not token:
        raise Unreachable(f"{host} verified the signature but minted no token: {minted}")
    if cache:
        remember(root, token, float(minted.get("expires", 0.0) or 0.0))
    return token


def remember(root: Path, token: str, expires: float) -> None:
    """Rewrite remote.json, keeping everything else in it — the `login` block
    lives in the same file and a session refresh must not eat it."""
    write_remote(root, {"token": token, "token_expires": expires})


def refresher(root: Path, config: dict[str, Any]) -> Callable[[], str] | None:
    """A way to mint ANOTHER session mid-process, or None when this project has no
    key to do it with — which is exactly what keeps a standing bearer token from
    being replaced behind its owner's back (`board.py::RemoteBoard.call`)."""
    door = as_object(config.get("login"))
    if not (door.get("host") and door.get("principal") and door.get("key")):
        return None
    return lambda: sign_in(
        root, str(door["host"]), str(door["principal"]), Path(str(door["key"])).expanduser()
    )


def _post(host: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
    """POST <host>/login, through the one decoder both clients share (`_wire.py`)
    — an unregistered key must arrive as the sentence naming how one gets
    registered, never as 'HTTP 409'."""
    return _wire.post(f"{host.rstrip('/')}/login", body, {}, timeout)
