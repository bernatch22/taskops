"""`taskops board` · `invite` · `revoke` — operating a HOST from the laptop, keyed.

    taskops board create <host>/<name>     owner only — THE way a board comes to exist
    taskops board ls [<host>]              owner: all of them; member: their own
    taskops board visibility <host>/<name> public|private   owner only
    taskops invite <who> --board <name>    owner only — prints the join line
    taskops revoke --key <SHA256:…> | --invite <id>

Every one of these is a signed call to the server's own `/rpc` (`http/admin.py`),
authenticated by the session an ssh key mints — `--key` on any of them signs in
on the spot, which is what makes the FIRST one runnable (`signed_in`). Before
them, all four were an ssh session on the box: the anomaly this chapter kills.

**THE BREAK-GLASS PATH SURVIVES**: `--root <dir>` runs the same act against the
files directly, on the machine that holds them, and it is what you use when the
server is down or the owner's key is lost. Not deprecated, never to be removed —
a system whose only door is its own API cannot be repaired when that API is what
broke. Those two acts live in `cli/admin.py`, beside `server init`: that module
runs ON the box, this one is the laptop.

**No host alias registry, and that is a decision.** `taskops host add prod …`
was the obvious next command and it is deliberately NOT here: the host is already
recorded, per project, in `remote.json`'s `login.host` — by the join that
registered the key, or by `taskops remote add <url>`, the same fact acquired
earlier and NOT the table that was refused. WHICH host and WHICH board a bare
call is about is `cli/remote.py`'s question, and it answers it once for all of
these verbs; `--key` has the same story (`identity.discover_key`). The explicit
`<host>/<name>` spelling is unchanged — it is the URL form, as in git.
"""

from __future__ import annotations

import argparse
from typing import Any
from pathlib import Path

from . import admin, commands
from .. import _wire, _clock, identity
from .._json import as_object
from ..board import find_root, read_config
from .remote import named, address, record_board
from .._errors import TaskopsError

TIMEOUT = 20.0


def board(args: argparse.Namespace) -> int:
    """`create` and `ls`. The target is `<host>/<name>` exactly as the card reads
    it, so the whole address is one argument and nothing has to be repeated."""
    action, target = str(args.action), str(args.target)
    if action == "visibility":
        return _visibility(args, target, str(getattr(args, "visibility", "") or ""))
    if action == "create":
        host, name = named(target)
        made = call(host, "board.create", {"name": name}, signed_in(host, args))
        record_board(find_root(Path.cwd()), host, str(made["board"]))
        print(f"{made['board']} created on {host} by {made['created_by']}")
        print(f"  invite somebody: taskops invite <who> --board {made['board']}")
        return 0
    host, _ = address(target)
    answer = call(host, "board.list", {}, signed_in(host, args))
    rows: list[dict[str, Any]] = [as_object(row) for row in answer.get("boards", [])]
    print(f"{host} — {len(rows)} board(s), as {answer.get('role', '?')}")
    for row in rows:
        print(f"  {row['name']:<24} {row['cards']:>4} cards  seq {row['seq']:<6} {_ago(row)}")
    return 0


def _visibility(args: argparse.Namespace, target: str, wanted: str) -> int:
    """`taskops board visibility <host>/<name> public|private` — the owner's call.

    It prints what public MEANS, every time, and not only the word it set: the
    command that opens a board to the world is the last place to be terse, and
    the reader is about to close the terminal. `recorded: false` is the board
    saying the value was already that — an unchanged fact writes no event
    (`verbs/project.py`), so re-running this is free and says so.
    """
    if not wanted and target in ("public", "private"):
        # `taskops board visibility public` — bare, so the ONE argument is the
        # visibility and not the board. argparse fills its positionals left to
        # right and cannot know that; the two vocabularies do not overlap.
        target, wanted = "", target
    host, name = named(target)
    if wanted not in ("public", "private"):
        raise TaskopsError(
            f"taskops board visibility {target} public|private — a board is one or the other"
        )
    out = call(host, "board.visibility", {"board": name, "visibility": wanted}, signed_in(host, args))
    moved = "already" if not out.get("recorded") else "now"
    print(f"{out['board']} on {host} is {moved} {out['visibility']} (by {out.get('by', '?')})")
    if out["visibility"] == "public":
        print("  anyone may READ it with no credential; every write still needs a registered key")
    else:
        print("  only a credential this host minted may read it")
    return 0


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


# ── the transport ───────────────────────────────────────────────────────────


def signed_in(host: str, args: argparse.Namespace, flag: str = "key") -> str:
    """The token these five verbs call with, and the whole of `--key` / `--as`.

    `identity.establish` is what makes this keyed rather than a token somebody
    pasted: an expired session is re-minted by signing the host's challenge, and
    a checkout that never joined signs in from the key on the command line —
    the ONLY way the owner's first ever command runs from the laptop (the
    deadlock is in `identity.NO_SESSION`). Nobody is asked for anything, and the
    `login` block is cached once the HOST accepted the signature, so the second
    command needs no flags. `flag` names where the key path is: on `revoke`,
    `--key` is already a FINGERPRINT — the thing being revoked — so there the
    one that signs you in is `--sign-key`."""
    root = find_root(Path.cwd())
    config = read_config(root)
    token, door = identity.establish(
        root, host, config, _flag(args, flag), _flag(args, "principal"), commands.principal()
    )
    if door and identity.is_own_host(config, host):
        identity.cache_login(root, door)
    return token


def _flag(args: argparse.Namespace, name: str) -> str:
    """A flag whose verb may not have declared it."""
    return str(getattr(args, name, "") or "")


def call(host: str, verb: str, args: dict[str, Any], token: str) -> dict[str, Any]:
    """One server-scope call, through the same decoder every other client uses.

    The envelope and the refusal come back through `_wire.post`, so the server's
    own sentence survives. The token is always the CALLER's — `push.py` signs in
    with the key it was handed, in a repo whose config still points at nothing,
    so looking one up here would find the empty local board."""
    return _wire.post(
        f"{host.rstrip('/')}/rpc",
        {"verb": verb, "args": args},
        {"Authorization": f"Bearer {token}"},
        TIMEOUT,
    )


def _ago(row: dict[str, Any]) -> str:
    active = float(row.get("active", 0.0) or 0.0)
    if not active:
        return "never used"
    minutes = max(0.0, (_clock.now() - active) / 60.0)
    return f"{minutes / 60:.0f}h ago" if minutes >= 60 else f"{minutes:.0f}m ago"
