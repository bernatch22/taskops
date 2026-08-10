"""`taskops invite` · `taskops revoke` — handing a credential out, and taking it back.

    taskops invite <who> --board <name>    owner only — prints the join line
    taskops revoke --key <SHA256:…> | --invite <id>

The laptop half of `http/grants.py`, and the split is that seam and not a line
count: `operate.py` is about a BOARD (create it, list them, say who may read it,
name the forge that opens it) and this is about a CREDENTIAL — the two never
share an argument. They do share the transport, which stays in `operate.py`
where `push.py` already reaches for it; a third module holding three lines of
`_wire.post` would be one more file to find and nothing to decide in it.

**THE BREAK-GLASS PATH SURVIVES** on both verbs: `--root <dir>` runs the same
act against the files directly, on the machine that holds them, and it is what
you use when the server is down or the owner's key is lost. Not deprecated,
never to be removed — a system whose only door is its own API cannot be
repaired when that API is what broke. Those two acts live in `cli/admin.py`,
beside `server init`: that module runs ON the box, this one is the laptop.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import admin
from .remote import address
from .operate import call, signed_in
from .._errors import TaskopsError


def invite(args: argparse.Namespace) -> int:
    """A one-time join line, minted by the server that will honour it."""
    who, name = str(args.who), str(args.board)
    if not who:
        raise TaskopsError("taskops invite <who> --board <name>")
    if args.root:  # break-glass: the files, on the box
        return admin.on_box_invite(Path(str(args.root)).expanduser(), who, name)
    if not name:
        raise TaskopsError("which board? taskops invite <who> --board <name>")
    host, _ = address(str(args.host))
    made = call(host, "invite.mint", {"who": who, "board": name}, signed_in(host, args))
    print(f"one-time invite for {who} (id {made['id']}, 7 days):")
    print(f"  taskops join \"{host}/{made['board']}?invite={made['token']}\" --key ~/.ssh/id_ed25519")
    return 0


def revoke(args: argparse.Namespace) -> int:
    """A key stops signing anybody in; an invite stops being redeemable."""
    key, ident = str(args.key), str(args.invite)
    if bool(key) == bool(ident):
        raise TaskopsError("taskops revoke --key <SHA256:…> | --invite <id> — exactly one")
    if args.root:  # break-glass: the files, on the box
        return admin.on_box_revoke(Path(str(args.root)).expanduser(), key, ident)
    host, _ = address(str(args.host))
    verb = "key.revoke" if key else "invite.revoke"
    gone = call(host, verb, {"key": key} if key else {"invite": ident}, signed_in(host, args, "sign_key"))
    print(f"revoked {key or ident} ({gone.get('principal') or gone.get('subject')}) on {host}")
    return 0
