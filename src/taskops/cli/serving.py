"""The commands that RUN something: `serve` and `ui`.

Split off `commands.py` — which is now only the two that CONNECT a repo to a
board (`init`, `join`) and the git hooks — when that module reached its 200-line
budget. The seam is not arbitrary: nothing here touches a repo, a hook or a
worktree, and nothing in `commands.py` starts a server. The HTTP server is
still imported inside each function, never at module scope: the CLI must start
without one.

`invite` used to live here and now lives in `operate.py` beside `board` and
`revoke` — the four acts that operate a HOST, which reach it over its API and
keep the on-box path as `--root`. Minting a credential is not "running
something": it was here because it opened the same sqlite file `serve` does.
"""

from __future__ import annotations

import json
import argparse
import webbrowser
from typing import TYPE_CHECKING
from pathlib import Path
from urllib.request import urlopen

if TYPE_CHECKING:  # a NAME for the annotation, never an import at start-up
    from ..http.upstream import Upstream

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
    # No `repo=`: this root is a directory of boards, not a checkout. /git
    # refuses here and says which case it is, rather than sniffing for a repo
    # that would be the wrong one anyway (ARCHITECTURE.md §16). The SAME
    # argument is why this host serves no dashboard either — a window needs a
    # clone to read a diff from, and /ui/ answers one sentence naming
    # `taskops ui` instead (`http/static.py`, which carries the post-mortem).
    httpd = make_server(root, str(args.host), int(args.port))
    host, port = httpd.server_address[0], httpd.server_address[1]
    print(f"taskops serving {root} on http://{host}:{port} — ctrl-c to stop")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        httpd.server_close()
    return 0


def ui(here: Path) -> int:
    """The dashboard, in one command with no parameters — ALWAYS served here.

    ONE window, and it stands in the checkout you ran it from. The UI ships
    inside the package, so there is nothing to build; the browser gets a freshly
    minted LOCAL token. The only thing a remote board changes is who answers
    `/board/rpc`: the local stores, or the server that owns the board, forwarded
    with the credential from `remote.json` (`http/upstream.py`, which is also
    where forwarding is argued against pointing the page at the remote).

    `/board/git/…` is mounted from THIS clone in both modes, and that is the
    reason the command changed. It used to redirect a remote board to
    `<server>/ui/?token=…` — a page served by a host that has no repository, so
    every patch in it fell through to a forge link or a sentence. The window was
    pointed at the wrong machine: the board is shared, the code is not, and a
    diff is read from the clone the reader actually has (ARCHITECTURE.md §16).

    The port and token persist in `.taskops/ui.json` (gitignored), so the link
    survives and a second `taskops ui` while one is running just reopens the
    browser. Serving blocks, like `taskops serve` — ctrl-c stops it. An agent
    runs it in the background; a human leaves the terminal open. No daemon to
    forget."""
    root = find_root(here)
    if not is_project(root):
        raise TaskopsError("no board here — taskops init starts one, taskops join connects one")
    upstream = _upstream(root)
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
    # `root` IS the checkout: `find_root` walked up to the directory holding
    # `.taskops`, and you cannot join a board without one. That is the whole
    # /git switch, decided here and passed once — `serve` below has a boards
    # directory instead and passes nothing, so its /git says so (§16).
    try:
        httpd = make_server(root / DIR, "127.0.0.1", port, repo=root, upstream=upstream)
    except OSError:  # the port moved on
        httpd = make_server(root / DIR, "127.0.0.1", 0, repo=root, upstream=upstream)
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


def _upstream(root: Path) -> Upstream | None:
    """The remote board this window looks at, or None for a board of our own.

    The refusal is `board.py::open_board`'s, word for word and on purpose: an
    address with no credential is the same broken join whichever door you came
    through, and one sentence to recognise beats two that nearly match."""
    from ..http.upstream import Upstream as Remote  # the CLI must start without a server

    config = read_config(root)
    url = str(config.get("url", ""))
    if not url:
        return None
    token = str(config.get("token", ""))
    if not token:
        raise TaskopsError(
            f"{root / DIR}/board.json points at {url} but there is no credential in "
            "remote.json — run: taskops join <url with ?token= or ?invite=>"
        )
    return Remote(url, token)


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
