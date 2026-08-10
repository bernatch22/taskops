"""Becoming somebody a host knows: burn an invite, enrol a pubkey.

Split out of `commands.py` at its own seam — `join` and `board push` both need
exactly this and only this: a repo with a local board has never joined
anything, so its first push may also be its first introduction to the host,
and there must not be two redemptions to keep in step.

There are two introductions now and they end in the SAME place: a pubkey this
host knows, and a session minted from it moments later. `redeem` burns an
invite somebody minted for you; `by_github` (`http/github.py` is the door)
lets a repo's membership stand in for that invite. Neither leaves a standing
credential behind, and the GitHub token in particular is a LOCAL — read here,
put in one request body, and gone with the frame.
"""

from __future__ import annotations

import os
import getpass
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


NO_KEY = (
    "--github enrols an ssh KEY, and there is none to enrol — GitHub introduces you once "
    "and the key is what signs you in from then on. Make one and try again:\n"
    "  ssh-keygen -t ed25519\n"
    "or point at an existing one: taskops join <board> --github --key <path>"
)

NO_TOKEN = (
    "no GitHub token, and nothing was sent. Any ONE of these gives me one:\n"
    "  gh auth login              the CLI's token is read automatically\n"
    "  export GITHUB_TOKEN=…      an environment variable\n"
    "  (or paste it at the hidden prompt)\n"
    "There is deliberately no --github <token>: a token in a flag lands in your shell "
    "history forever, and this one is only ever used for a single call."
)


def by_github(base: str, who: str, public: str) -> dict[str, str]:
    """GitHub vouches for you ONCE, and what stays behind is your pubkey.

    The token is fetched here, travels in this one request body, and is never
    returned, printed, cached or written: what comes back names the principal
    this host now knows and the repo that proved it, and the caller's very next
    act is the ordinary `/login` challenge with the key just enrolled. That is
    why nothing in this function can put a GitHub token in `remote.json` — it
    has none to put there by the time `join` writes the file.
    """
    if not public:
        raise TaskopsError(NO_KEY)
    data = post_json(
        f"{base.rstrip('/')}/join/github",
        {"github_token": github_token(), "principal": who, "pubkey": public},
        {},
        20.0,
    )
    return {
        "actor": str(data.get("actor", f"dev:{who}")),
        "repo": str(data.get("repo", "")),
        "need": str(data.get("need", "")),
    }


def github_token() -> str:
    """WHERE the token comes from, in order — and never from a flag value.

    `gh auth token` first, because the CLI is already installed and already
    authenticated on the machine of anybody who has push on a repo, so the
    common case asks the human nothing. Then `$GITHUB_TOKEN`, which is how CI
    and a shell that never installed `gh` say it. Then a HIDDEN prompt.

    **A flag is not one of the sources and must never become one.** `--github`
    takes no value: a secret passed as an argument is written to
    `~/.zsh_history` by the shell before the process starts, survives every
    rotation of the token, and is visible in `ps` to every user on the box
    while the command runs. The prompt is the fallback precisely because it is
    the one input that leaves no trace.
    """
    from ..gitwork import run

    try:
        asked = run.tool("gh", "auth", "token", timeout=20.0)
    except TaskopsError:
        asked = None  # no `gh` on PATH, or it hung — the next source answers
    if asked is not None and asked.ok and asked.out.strip():
        return asked.out.strip()
    if os.environ.get("GITHUB_TOKEN", "").strip():
        return os.environ["GITHUB_TOKEN"].strip()
    typed = getpass.getpass("GitHub token (input hidden, used once, stored nowhere): ").strip()
    if not typed:
        raise TaskopsError(NO_TOKEN)
    return typed


def host_of(base: str) -> str:
    """The SERVER, out of a board address: `/login` is server scope, not a board's."""
    return base.rstrip("/").rpartition("/")[0]
