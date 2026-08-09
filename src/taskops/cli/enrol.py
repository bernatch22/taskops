"""Becoming somebody a host knows: burn an invite, enrol a pubkey.

Split out of `commands.py` at its own seam — `join` and `board push` both need
exactly this and only this: a repo with a local board has never joined
anything, so its first push may also be its first introduction to the host,
and there must not be two redemptions to keep in step.
"""

from __future__ import annotations

from pathlib import Path

from .._wire import post as post_json
from .._errors import TaskopsError


def redeem(base: str, invite: str, who: str, public: str = "") -> tuple[str, str]:
    """Burn an invite, and enrol the key travelling with it."""
    body: dict[str, str] = {"invite": invite, "who": who}
    if public:
        body["pubkey"] = public
    data = post_json(f"{base.rstrip('/')}/invite/redeem", body, {}, 20.0)
    return str(data.get("token", "")), str(data.get("actor", f"dev:{who}"))


def pubkey(key: str) -> str:
    """The PUBLIC half of `--key`, read from `<key>.pub` — never the private key,
    which never leaves this machine and which `store/pubkeys.py` refuses by name
    if it is ever sent by mistake."""
    if not key:
        return ""
    private = Path(key).expanduser()
    public = private if private.suffix == ".pub" else Path(f"{private}.pub")
    try:
        return public.read_text(encoding="utf-8").strip()
    except OSError as err:
        raise TaskopsError(
            f"cannot read {public} — --key takes the PRIVATE key (the one ssh-keygen signs "
            f"with); its .pub next to it is what gets registered: {err}"
        ) from err


def host_of(base: str) -> str:
    """The SERVER, out of a board address: `/login` is server scope, not a board's."""
    return base.rstrip("/").rpartition("/")[0]
