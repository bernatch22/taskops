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
failed login into the caller's error."""

from __future__ import annotations

from typing import Any, Callable
from pathlib import Path

from . import _wire, _clock
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

IDENTITIES = ("id_ed25519", "id_ecdsa", "id_rsa")
"""ssh's OWN identity files, in ssh's own order (`ssh_config(5)`, IdentityFile).
`--key` stays as the override, exactly as `ssh -i` is, and this tuple is the one
place the order lives: six verbs each guessing it is six places for it to drift."""
TRIED = ", ".join(f"~/.ssh/{name}" for name in IDENTITIES)

NO_SESSION = (
    "no session for {host}, and no ssh key to make one with — tried {tried}. Sign in "
    "with your ssh key: add --key <path> (and --as <principal> when your unix user is "
    "not that name), or join the host first: taskops join <url>?invite=… "
    "--key ~/.ssh/id_ed25519"
)
"""The refusal every operate verb hands back, and it names BOTH doors on purpose.

It used to name only `join`, the wrong sentence for the one person who cannot
follow it: the OWNER on day one, whose invite is minted by `taskops invite`,
which wants a session of its own for a board nobody has created — a deadlock
whose only exit was ssh onto the box, the anomaly this chapter kills (found by
running the flow on a clean host, 2026-08-09; every test had already joined)."""


def establish(
    root: Path,
    host: str,
    config: dict[str, Any],
    key: str = "",
    principal: str = "",
    default: str = "",
    refusal: str = "",
) -> tuple[str, dict[str, str] | None]:
    """A token for `host`, and the `login` block that would let it renew itself.

    ONE implementation of "how does this laptop become authorised", for the six
    verbs that operate a host plus `board push`. Given `--key` it signs in on the
    spot — no join, no invite, nothing recorded here first — which is what makes
    the owner's FIRST command runnable from the laptop. Without one it is the
    cached session (`fresh`), exactly as before.

    The principal is `--as`, else the one the last login used, else `default`
    (the caller's $USER guess — a cli fact, so it arrives as an argument rather
    than being read here). `--as` exists because that guess is wrong on any
    machine whose unix user is not the principal's name, and until it existed
    such a machine could not sign in at all.

    The `login` block is RETURNED and never written: `push.py` writes it in its
    own step 5 and not a moment earlier, because the order of that command is
    its safety. A caller with nothing to sequence uses `cache_login`.

    With no `--key` and no cached session it is DISCOVERED (`discover_key`)."""
    if not key:
        token = fresh(root, config, _clock.now())
        if token:
            return token, None
        found = discover_key()
        if not found:
            raise TaskopsError((refusal or NO_SESSION).format(host=host, tried=TRIED))
        key = str(found)
    named = principal_for(config, principal, default)
    path = Path(key).expanduser()
    door = {"host": host, "principal": named, "key": str(path)}
    return sign_in(root, host, named, path, cache=is_own_host(config, host)), door


def discover_key() -> Path | None:
    """The first of ssh's identity files that EXISTS, or None when none does.
    `establish` is its only caller on purpose: discovery is a DEFAULT for
    `--key`, never a second way in — everything after it is the one sign-in."""
    return next((p for p in (Path.home() / ".ssh" / n for n in IDENTITIES) if p.is_file()), None)


def principal_for(config: dict[str, Any], principal: str = "", default: str = "") -> str:
    """WHO is signing in: `--as`, else the last login's principal, else the guess.

    Public because `board push --invite` has to redeem the invite under the same
    name it is about to sign in as, one call earlier — two derivations of that
    name would be one drift away from an invite burnt for the wrong person."""
    return principal or str(as_object(config.get("login")).get("principal") or "") or default


def is_own_host(config: dict[str, Any], host: str) -> bool:
    """Is `host` the one this checkout's session cache is ABOUT? `remote.json`
    holds ONE session, for the board this repo reads; operating a DIFFERENT
    server from inside a joined checkout is legitimate and must leave it alone,
    or the next ordinary call goes out with a token another host minted."""
    named = str(as_object(config.get("login")).get("host", ""))
    return not named or named.rstrip("/") == host.rstrip("/")


def cache_login(root: Path, door: dict[str, str]) -> None:
    """Remember WHICH key signed in, so the next command needs no flags at all.
    Written only once the host ACCEPTED the signature: a `--key` naming a key it
    never registered must leave the config saying nothing, not something false."""
    write_remote(root, {"login": door})


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
    for a host this checkout is not joined to (`is_own_host`)."""
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
