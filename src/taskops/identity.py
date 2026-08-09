"""WHO signs in, and WITH WHICH key — the identity half of the ssh login.

Split out of `session.py` at its own seam: this file answers "how does this
laptop become authorised" (discover a key, resolve the principal, decide
whether the session may be cached); `session.py` keeps the token lifecycle
(mint, refresh, remember). `establish` is the one entry the six operate verbs
plus `board push` share.
"""

from __future__ import annotations

from typing import Any
from pathlib import Path

from . import _clock, session
from ._json import as_object
from ._errors import TaskopsError
from ._locate import write_remote

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
    cached session (`session.fresh`), exactly as before.

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
        token = session.fresh(root, config, _clock.now())
        if token:
            return token, None
        found = discover_key()
        if not found:
            raise TaskopsError((refusal or NO_SESSION).format(host=host, tried=TRIED))
        key = str(found)
    named = principal_for(config, principal, default)
    path = Path(key).expanduser()
    door = {"host": host, "principal": named, "key": str(path)}
    return session.sign_in(root, host, named, path, cache=is_own_host(config, host)), door


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
