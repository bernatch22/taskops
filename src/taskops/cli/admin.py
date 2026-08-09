"""`taskops server …` — operating the HOST, as opposed to a board.

    taskops server init --root <dir> --key <path.pub> [--owner <name>]

This is the ONE command in taskops that is meant to be run over ssh, and only
this one. Everything else a server owner does — create a board, list them,
invite, revoke — is a signed call over the API from the laptop, which is the
whole point of the chapter: v1 had no notion of an owner, so every admin act
escaped the CLI into `ssh box "…"` plus a scp of somebody's `events.jsonl`.

Why the bootstrap cannot follow: authorising it would need a credential this
host does not have yet. Trust enters through a channel that predates the
system, and the machine's own shell is that channel — `store/server.py` carries
the argument in full.
"""

from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path

from .. import _clock
from .._errors import TaskopsError
from ..core.scope import ROLE_OWNER
from ..store.server import SIGNERS, ServerStore


def server(args: argparse.Namespace) -> int:
    if str(args.action) != "init":
        raise TaskopsError(f"taskops server {args.action}: unknown — this host knows: init")
    return init(
        Path(str(args.root)).expanduser(),
        str(args.key),
        str(args.owner) or _whoami(),
    )


def init(root: Path, key: str, owner: str) -> int:
    """Record the first principal as OWNER, from a pubkey on disk or on stdin."""
    store = ServerStore(root)
    try:
        held = store.owner()
        if held is not None and held.name != owner:
            raise TaskopsError(
                f"{root} is already owned by {held.name!r} — "
                "a second owner is not a thing; register a member instead"
            )
        recorded = store.enroll(owner, ROLE_OWNER, _keyline(key), _clock.now())
    finally:
        store.close()
    print(f"{root} is owned by {owner} — {recorded.fingerprint}")
    print(f"  signers: {root / SIGNERS}")
    print(f"  serve it: taskops serve --root {root}")
    return 0


def _keyline(key: str) -> str:
    """The pubkey itself: a path, or `-` for stdin. Never a private key — the
    grammar in `store/pubkeys.py` refuses one by name."""
    if not key:
        raise TaskopsError("no key — pass --key ~/.ssh/id_ed25519.pub (or --key - for stdin)")
    if key == "-":
        return sys.stdin.read()
    path = Path(key).expanduser()
    try:
        return path.read_text(encoding="utf-8")
    except OSError as err:
        raise TaskopsError(f"cannot read {path}: {err}") from err


def _whoami() -> str:
    return os.environ.get("USER", "owner")


# ── break-glass: a board act, against the FILES, on the box ─────────────────
#
# `operate.py` runs these four acts over the API, keyed, from the laptop — that
# is the chapter. They live HERE because this module is the one that runs ON the
# machine, and `--root <dir>` is the same channel `server init` uses: the shell
# of the box, which predates the API and is what you have left when the API is
# what broke. Not deprecated, and not to be removed.


def on_box_invite(root: Path, who: str, board: str) -> int:
    from ..store.creds import WEEK, Credentials

    creds = Credentials(root / "live.sqlite")
    name = board or Path.cwd().name
    token, credential = creds.mint(f"invite:{who}", name, _clock.now(), ttl=WEEK, once=True)
    creds.close()
    print(f"one-time invite for {who} (id {credential.id}, 7 days):")
    print(f"  taskops join https://<host>/{name}?invite={token}")
    return 0


def on_box_revoke(root: Path, key: str, ident: str) -> int:
    from ..store.creds import Credentials
    from ..store.server import ServerStore

    if key:
        store = ServerStore(root)
        store.revoke_key(key)
        store.close()
    else:
        creds = Credentials(root / "live.sqlite")
        creds.revoke(ident)
        creds.close()
    print(f"revoked {key or ident} in {root}")
    return 0
