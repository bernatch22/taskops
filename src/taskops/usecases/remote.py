"""The one remote a project syncs with: a URL, a secret, and two cursors.

ONE remote per project. A second `add` is refused by naming the first: two remotes means two
cursors over two logs and a report that has to answer "who saw more" three ways, and none of
that is designed. Federation is a different feature with a different shape.

The token lives inside the block `taskops init` gitignores — that block lists what under
`.taskops/` is NOT committed and its one hole is `events.jsonl`, so `remote.json` is ignored
by construction. `tests/e2e/test_remote.py` pins it: a token reaching a commit is
unrecoverable in the only sense that matters, since rotating it is work somebody has to
notice they need to do. The file mechanics (0600, atomic-enough writes) live in `_remotefile`.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from .._errors import BadRequest, NotInitialized
from ..contracts import Remote
from ..storage import resolve_root
from ._remotefile import REMOTE_FILE, load, remote_path, write
from ._sessionfile import as_credential, session_for

__all__ = ["REMOTE_FILE", "add_remote", "read_remote", "require_remote",
           "remove_remote", "save_cursor", "save_pushed", "remote_path"]

read_remote = load


def add_remote(start: Path | str, url: str, token: str = "") -> Remote:
    """Register the one remote. Refuses a second by naming the one already there.

    With no token, the session `taskops login` stored for that server is used instead — which
    is the whole point of logging in: a teammate runs three commands and never handles a
    secret. The lookup is by URL prefix because what is passed here is `<server>/<project>`.
    """
    root = resolve_root(start)
    address = url.strip().rstrip("/")
    if not address.startswith(("http://", "https://")):
        raise BadRequest(f"`{url}` is not a server address — pass the base URL, "
                         f"like https://taskops.example.com")
    credential = token.strip() or _from_session(address)
    already = read_remote(start)
    if already is not None:
        raise BadRequest(f"this project already syncs with {already['url']} — one remote per "
                         f"project; run `taskops remote remove` first")
    return write(root, Remote(url=address, token=credential, pushed=0, cursor=0))


def _from_session(address: str) -> str:
    """The session credential for that server, or the error that names BOTH ways out — a
    person who has neither needs to know that logging in is an option, and a person on a
    server without GitHub auth needs to know that a token still works."""
    found = session_for(address)
    if found is None:
        raise BadRequest(f"no token and no session for {address} — either pass "
                         f"`--token <token>`, or run `taskops login <server-url>` to sign in "
                         f"with your GitHub account")
    return as_credential(found["session"])


def require_remote(start: Path | str) -> Remote:
    """The remote, or the one line that says how to get one."""
    found = read_remote(start)
    if found is None:
        raise NotInitialized("no remote configured — run `taskops remote add <url> "
                             "--token <token>`, or keep syncing through git with `taskops sync`")
    return found


def remove_remote(start: Path | str) -> str:
    """Forget the remote AND the token. Returns the url that was dropped."""
    gone = require_remote(start)
    remote_path(resolve_root(start)).unlink(missing_ok=True)
    return gone["url"]


def save_cursor(start: Path | str, cursor: int) -> None:
    """Record how far this machine has read the SERVER's log. Never moves backwards."""
    _advance(start, "cursor", cursor)


def save_pushed(start: Path | str, pushed: int) -> None:
    """Record how far this machine's OWN log has been sent up. Its own number — the two
    cursors count different logs and may never be compared (see the contract)."""
    _advance(start, "pushed", pushed)


def _advance(start: Path | str, field: str, value: int) -> None:
    current = require_remote(start)
    if value > int(current[field]):                     # type: ignore[literal-required]
        stored = dict(current)
        stored[field] = int(value)
        write(resolve_root(start), cast("Remote", stored))
