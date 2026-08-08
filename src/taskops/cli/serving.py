"""The commands that RUN something: `serve`, `invite`, `ui`.

Split off `commands.py` — which is now only the two that CONNECT a repo to a
board (`init`, `join`) and the git hooks — when that module reached its 200-line
budget. The seam is not arbitrary: nothing here touches a repo, a hook or a
worktree, and nothing in `commands.py` starts a server. The HTTP server is
still imported inside each function, never at module scope: the CLI must start
without one.
"""

from __future__ import annotations

import json
import argparse
import webbrowser
from pathlib import Path
from urllib.request import urlopen

from .. import _clock
from .._json import as_object
from ..board import DIR, find_root, is_project, read_config
from .._errors import TaskopsError
from .commands import actor


def serve(args: argparse.Namespace) -> int:
    from ..http.server import (
        serve as make_server,  # imported here: the CLI must start without a server
    )

    root = Path(str(args.root)).expanduser()
    ui_path = Path(str(args.ui)).expanduser() if args.ui else None
    httpd = make_server(root, str(args.host), int(args.port), ui_path)
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


def ui(here: Path) -> int:
    """The dashboard, in one command with no parameters.

    Remote board: open its /ui/ WITH the credential from remote.json — the old
    `open` sent people to a paste-a-token screen holding a token the machine
    already had. Local board: serve it right here (the UI ships inside the
    package) and open the browser with a freshly minted token. The port and
    token persist in `.taskops/ui.json` (gitignored), so the link survives and
    a second `taskops ui` while one is running just reopens the browser.

    Serving blocks, like `taskops serve` — ctrl-c stops it. An agent runs it
    in the background; a human leaves the terminal open. No daemon to forget."""
    root = find_root(here)
    config = read_config(root)
    if config.get("url"):
        return _open(f"{str(config['url']).rstrip('/')}/ui/?token={config.get('token', '')}")
    if not is_project(root):
        raise TaskopsError("no board here — taskops init starts one, taskops join connects one")
    state = as_object(json.loads((root / DIR / "ui.json").read_text())) if (
        root / DIR / "ui.json"
    ).exists() else {}
    port, token = int(state.get("port", 0) or 0), str(state.get("token", ""))
    if port and _healthy(port):
        return _open(f"http://127.0.0.1:{port}/board/ui/?token={token}")
    from ..http.server import serve as make_server  # the CLI must start without a server

    if not token:
        from ..store.creds import Credentials

        creds = Credentials(root / DIR / "live.sqlite")
        token, _ = creds.mint(actor(), "board", _clock.now(), caps="read,write")
        creds.close()
    try:
        httpd = make_server(root / DIR, "127.0.0.1", port)
    except OSError:
        httpd = make_server(root / DIR, "127.0.0.1", 0)  # the old port is somebody else's now
    port = httpd.server_address[1]
    (root / DIR / "ui.json").write_text(json.dumps({"port": port, "token": token}) + "\n")
    _open(f"http://127.0.0.1:{port}/board/ui/?token={token}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        httpd.server_close()
    return 0


def _open(url: str) -> int:
    print(url)  # ALWAYS printed: a headless session cannot read a browser tab
    webbrowser.open(url)
    return 0


def _healthy(port: int) -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1) as answer:  # noqa: S310
            return bool(as_object(json.loads(answer.read().decode())).get("ok"))
    except (OSError, ValueError):
        return False
