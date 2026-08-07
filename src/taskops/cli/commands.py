"""What each command actually does. `main.py` only parses and dispatches."""

from __future__ import annotations

import os
import sys
import json
import argparse
from pathlib import Path
from urllib.request import Request, urlopen

from .. import _clock
from .._json import query, as_object
from ..board import DIR, find_root, open_board
from .._errors import TaskopsError
from ..gitwork import run, bind, install, trailer

# ── the commands ────────────────────────────────────────────────────────────


def init(here: Path) -> int:
    root = find_root(here)
    (root / DIR / "board").mkdir(parents=True, exist_ok=True)
    (root / DIR / "board.json").write_text("{}\n", encoding="utf-8")
    _wire(root, actor())
    print(f"local board in {root / DIR / 'board'} — the MCP tools are the way in")
    return 0


def join(here: Path, url: str, given: str) -> int:
    root = find_root(here)
    base = url.partition("?")[0]
    params = query(url)
    who = given or actor()
    token = params.get("token", "")
    if params.get("invite", ""):
        token, who = _redeem(base, params["invite"], who.partition(":")[2] or "me")
    if not token:
        raise TaskopsError("that URL carries no ?token= or ?invite= — ask for a fresh link")
    install.write_config(root, base.rstrip("/"), token)
    _wire(root, who)
    print(f"joined {base} as {who}. Hooks installed; the board is in MCP.")
    return 0


def serve(args: argparse.Namespace) -> int:
    from ..http.server import (
        serve as make_server,  # imported here: the CLI must start without a server
    )

    root = Path(str(args.root)).expanduser()
    ui = Path(str(args.ui)).expanduser() if args.ui else None
    httpd = make_server(root, str(args.host), int(args.port), ui)
    host, port = httpd.server_address[0], httpd.server_address[1]
    print(f"taskops serving {root} on http://{host}:{port} — ctrl-c to stop")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        httpd.server_close()
    return 0


def invite(args: argparse.Namespace) -> int:
    from ..store.creds import Credentials

    root = Path(str(args.root)).expanduser()
    creds = Credentials(root / "live.sqlite")
    if args.revoke:
        creds.revoke(str(args.revoke))
        print(f"revoked {args.revoke}")
        return 0
    board = str(args.board) or Path.cwd().name
    token, credential = creds.mint(
        f"invite:{args.who}", board, _clock.now(), ttl=7 * 24 * 3600, once=True
    )
    print(f"one-time invite for {args.who} (id {credential.id}, 7 days):")
    print(f"  taskops join https://<host>/{board}?invite={token}")
    return 0


def hook(here: Path, which: str, rest: list[str]) -> int:
    """The two GIT hooks; `hook claude` is routed in `main` and never prints.

    Neither of these may block a commit. Failures print and return 0.
    """
    root = find_root(here)
    if which == "trailer":
        if rest:
            trailer.stamp_file(Path(rest[0]), run.branch_at(here))
        return 0
    facts = bind.commit_facts(here)
    if facts is None:
        return 0
    try:
        board = open_board(root, actor())
        bind.record(board, root, facts)
        bind.drain(board, root)
    except TaskopsError as err:
        print(f"taskops: {err}", file=sys.stderr)  # visible, never swallowed
    bind.push_card(here, str(facts["branch"]))
    return 0


# ── plumbing ────────────────────────────────────────────────────────────────


def actor() -> str:
    """`TASKOPS_ACTOR` wins — that is how a spawned worker knows who it is."""
    return os.environ.get("TASKOPS_ACTOR") or f"dev:{os.environ.get('USER', 'me')}"


def _wire(root: Path, who: str) -> None:
    install.install_hooks(root, sys.executable)
    install.write_gitignore(root)
    install.write_mcp(root, sys.executable, who)
    install.write_claude_hooks(root, sys.executable)  # delivery only — MENTIONS.md §9


def _redeem(base: str, invite: str, who: str) -> tuple[str, str]:
    request = Request(
        f"{base.rstrip('/')}/invite/redeem",
        data=json.dumps({"invite": invite, "who": who}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:  # noqa: S310 — the URL is the user's
            body: object = json.loads(response.read().decode())
    except OSError as err:
        raise TaskopsError(f"{base} did not answer: {err}") from err
    envelope = as_object(body)
    if not envelope.get("ok"):
        raise TaskopsError(f"that invite was refused: {body}")
    data = as_object(envelope.get("data"))
    return str(data.get("token", "")), str(data.get("actor", f"dev:{who}"))
