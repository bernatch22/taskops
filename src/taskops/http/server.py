"""The taskops server: boards mounted by name, one door each.

    POST /login                  an ssh key signs a challenge, gets a session token
    POST /rpc                    the HOST's own verbs: create a board, list, invite, revoke
    POST /<board>/rpc            every verb, read and write
    GET  /<board>/feed           WebSocket (SSE fallback) — the UI's live wire
    POST /<board>/invite/redeem  burn an invite, get a personal credential
    GET  /<board>/git/* · /ui/*  diffs and the bundle, ONLY on a host inside a repo
    GET  /healthz

The boards themselves live in `mounts.py`; the routing itself — one method per
door — is `handler.py`. This file is the server's lifecycle: who owns the
mounts, and when they close.

The SAME routes serve a window onto a remote board (`taskops ui` in a joined checkout): only
`/<board>/rpc` changes hands, forwarded to the server that owns it (`upstream.py`), while /ui
and /git stay local — the page cannot tell, so the committed bundle is untouched by it. A
BOARD HOST opens neither door that needs a clone (`gitdoor.py::NO_REPO`, `static.py::NO_UI`).
A PUBLIC board answers every READ door as `anon`, with no credential (`auth.py::anonymous`).
"""

from __future__ import annotations

import sys
from typing import Any
from pathlib import Path
from http.server import ThreadingHTTPServer

from .mounts import Mounts
from .handler import Handler
from .upstream import Upstream


class BoardServer(ThreadingHTTPServer):
    """A threading server that owns its mounts — no module-level state anywhere, so one
    process runs three independent boards without them seeing each other."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], mounts: Mounts) -> None:
        self.mounts = mounts
        super().__init__(address, Handler)

    def server_close(self) -> None:
        super().server_close()
        self.mounts.close()

    def handle_error(self, request: Any, client_address: Any) -> None:
        """A client that hung up is NOT an error, and printing it as one is worse
        than silence: it teaches a reader to skim tracebacks.

        A browser opens several keep-alive connections per origin and closes the
        spares once the page settles; a WebSocket upgrade replaces one outright.
        `socketserver` answers every exception in its thread with a full
        traceback, so a perfectly healthy `taskops ui` printed a stack per
        disconnect — thirty lines of Python internals under a page that was
        working, which is exactly how a real fault stops being visible.

        Everything else still prints, unchanged. The rule this file already
        holds for the request log holds here too: a broken server is seen, never
        swallowed. A departure is not a break."""
        if isinstance(sys.exc_info()[1], (ConnectionResetError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


def serve(root: Path, host: str = "127.0.0.1", port: int = 8787, repo: Path | None = None,
          upstream: Upstream | None = None) -> BoardServer:
    """A server, not yet running. The caller decides the thread and the lifetime,
    whether it sits in a repo (`repo` — what mounts /git AND the bundle, §16), and
    whether it OWNS the board or is a window onto somebody else's (`upstream`)."""
    return BoardServer((host, port), Mounts(root, repo, upstream))
