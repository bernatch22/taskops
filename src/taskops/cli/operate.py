"""`taskops board` · `invite` · `revoke` — operating a HOST from the laptop, keyed.

    taskops board create <host>/<name>     owner only — THE way a board comes to exist
    taskops board ls [<host>]              owner: all of them; member: their own
    taskops invite <who> --board <name>    owner only — prints the join line
    taskops revoke --key <SHA256:…> | --invite <id>

Every one of these is a signed call to the server's own `/rpc` (`http/admin.py`),
authenticated by the session an ssh key mints. Before them, all four were an ssh
session on the box — which is the anomaly this chapter exists to kill.

**THE BREAK-GLASS PATH SURVIVES**: `--root <dir>` runs the same act against the
files directly, on the machine that holds them, and it is what you use when the
server is down or the owner's key is lost. It is not deprecated and must not be
removed — a system whose only door is its own API cannot be repaired when that
API is what broke.

**No host alias registry, and that is a decision.** `taskops host add prod …`
was the obvious next command and it is deliberately NOT here: the host is
already recorded, per project, by the join that registered the key —
`remote.json`'s `login.host` (`session.py`). So inside a checkout no host
argument is needed at all, and outside one a URL is a paste. An alias table
would be a THIRD place a server's address lives, next to `board.json` and
`remote.json`, and the first of the three to drift.
"""

from __future__ import annotations

import argparse
from typing import Any
from pathlib import Path

from .. import _wire, _clock, session
from .._json import as_object
from ..board import find_root, read_config
from .._errors import TaskopsError

TIMEOUT = 20.0

NO_HOST = (
    "which host? Pass --host https://<host>, or run this in a checkout joined to one "
    "with `taskops join <url> --key ~/.ssh/id_ed25519` (the join is what records it)"
)


def board(args: argparse.Namespace) -> int:
    """`create` and `ls`. The target is `<host>/<name>` exactly as the card reads
    it, so the whole address is one argument and nothing has to be repeated."""
    action, target = str(args.action), str(args.target)
    if action == "create":
        host, name = _address(target)
        if not name:
            raise TaskopsError("taskops board create <host>/<name> — which board?")
        made = _call(host, "board.create", {"name": name})
        print(f"{made['board']} created on {host} by {made['created_by']}")
        print(f"  invite somebody: taskops invite <who> --board {made['board']}")
        return 0
    host, _ = _address(target)
    answer = _call(host, "board.list", {})
    rows: list[dict[str, Any]] = [as_object(row) for row in answer.get("boards", [])]
    print(f"{host} — {len(rows)} board(s), as {answer.get('role', '?')}")
    for row in rows:
        print(f"  {row['name']:<24} {row['cards']:>4} cards  seq {row['seq']:<6} {_ago(row)}")
    return 0


def invite(args: argparse.Namespace) -> int:
    """A one-time join line, minted by the server that will honour it."""
    who, name = str(args.who), str(args.board)
    if not who:
        raise TaskopsError("taskops invite <who> --board <name>")
    if args.root:  # break-glass: the files, on the box
        return _on_box_invite(Path(str(args.root)).expanduser(), who, name)
    if not name:
        raise TaskopsError("which board? taskops invite <who> --board <name>")
    host, _ = _address(str(args.host))
    made = _call(host, "invite.mint", {"who": who, "board": name})
    print(f"one-time invite for {who} (id {made['id']}, 7 days):")
    print(f"  taskops join \"{host}/{made['board']}?invite={made['token']}\" --key ~/.ssh/id_ed25519")
    return 0


def revoke(args: argparse.Namespace) -> int:
    """A key stops signing anybody in; an invite stops being redeemable."""
    key, ident = str(args.key), str(args.invite)
    if bool(key) == bool(ident):
        raise TaskopsError("taskops revoke --key <SHA256:…> | --invite <id> — exactly one")
    if args.root:  # break-glass: the files, on the box
        return _on_box_revoke(Path(str(args.root)).expanduser(), key, ident)
    host, _ = _address(str(args.host))
    verb = "key.revoke" if key else "invite.revoke"
    gone = _call(host, verb, {"key": key} if key else {"invite": ident})
    print(f"revoked {key or ident} ({gone.get('principal') or gone.get('subject')}) on {host}")
    return 0


# ── the transport ───────────────────────────────────────────────────────────


def _call(host: str, verb: str, args: dict[str, Any]) -> dict[str, Any]:
    """One server-scope call, through the same decoder every other client uses.

    `session.fresh` is what makes this keyed rather than a token somebody pasted:
    an expired session is re-minted here by signing the host's challenge, and
    nobody is asked for anything (`session.py`). The envelope and the refusal
    come back through `_wire.post`, so the server's own sentence survives."""
    root = find_root(Path.cwd())
    token = session.fresh(root, read_config(root), _clock.now())
    if not token:
        raise TaskopsError(
            f"no session for {host} — join it with a key first: "
            "taskops join <url>?invite=… --key ~/.ssh/id_ed25519"
        )
    return _wire.post(
        f"{host.rstrip('/')}/rpc",
        {"verb": verb, "args": args},
        {"Authorization": f"Bearer {token}"},
        TIMEOUT,
    )


def _address(target: str) -> tuple[str, str]:
    """`<host>/<name>`, `<host>`, `<name>` or nothing — into (host, name).

    A URL is recognised by its scheme and never by counting slashes: `https://h/b`
    has three and `h/b` has one, and guessing between them is how a board called
    `https:` gets created."""
    text = target.strip().rstrip("/")
    if "://" in text:
        base, _, name = text.rpartition("/")
        return (text, "") if base.endswith(":/") else (base, name)
    host = _joined_host()
    if not host:
        raise TaskopsError(NO_HOST)
    return host, text


def _joined_host() -> str:
    """The server this checkout is joined to, from the block `join --key` wrote."""
    root = find_root(Path.cwd())
    return str(as_object(read_config(root).get("login")).get("host", ""))


def _ago(row: dict[str, Any]) -> str:
    active = float(row.get("active", 0.0) or 0.0)
    if not active:
        return "never used"
    minutes = max(0.0, (_clock.now() - active) / 60.0)
    return f"{minutes / 60:.0f}h ago" if minutes >= 60 else f"{minutes:.0f}m ago"


# ── break-glass: the same acts, against the files, on the box ───────────────


def _on_box_invite(root: Path, who: str, board: str) -> int:
    from ..store.creds import WEEK, Credentials

    creds = Credentials(root / "live.sqlite")
    name = board or Path.cwd().name
    token, credential = creds.mint(f"invite:{who}", name, _clock.now(), ttl=WEEK, once=True)
    creds.close()
    print(f"one-time invite for {who} (id {credential.id}, 7 days):")
    print(f"  taskops join https://<host>/{name}?invite={token}")
    return 0


def _on_box_revoke(root: Path, key: str, ident: str) -> int:
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
