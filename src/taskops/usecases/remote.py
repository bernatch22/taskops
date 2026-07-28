"""`.taskops/remote.json` — where this project syncs, and the secret that proves who it is.

The file is written through `os.open` with mode 0600 rather than `write_text` followed by a
`chmod`, because the two-step version publishes the token to every user on the machine for
the width of one syscall. It is also inside the block `taskops init` gitignores: that block
lists what under `.taskops/` is NOT committed and its one hole is `events.jsonl`, so a file
added here is ignored by construction. `tests/e2e/test_remote.py` pins both facts — a token
reaching a commit is unrecoverable in the only sense that matters, since rotating it is work
somebody has to notice they need to do.

ONE remote per project. A second `add` is refused by naming the first: two remotes means two
cursors over two logs and a report that has to answer "who saw more" three ways, and none of
that is designed. Federation is a different feature with a different shape.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

from .._errors import BadRequest, NotInitialized
from ..contracts import Remote
from ..storage import PROJECT_DIR, resolve_root

__all__ = ["REMOTE_FILE", "add_remote", "read_remote", "require_remote",
           "remove_remote", "save_cursor", "remote_path"]

REMOTE_FILE = f"{PROJECT_DIR}/remote.json"


def remote_path(root: Path) -> Path:
    return root / REMOTE_FILE


def add_remote(start: Path | str, url: str, token: str) -> Remote:
    """Register the one remote. Refuses a second by naming the one already there."""
    root = resolve_root(start)
    address = url.strip().rstrip("/")
    if not address.startswith(("http://", "https://")):
        raise BadRequest(f"`{url}` is not a server address — pass the base URL, "
                         f"like https://taskops.example.com")
    if not token.strip():
        raise BadRequest("a remote needs a token — the server rejects every call without one")
    already = read_remote(start)
    if already is not None:
        raise BadRequest(f"this project already syncs with {already['url']} — one remote per "
                         f"project; run `taskops remote remove` first")
    return _write(root, Remote(url=address, token=token.strip(), cursor=0))


def read_remote(start: Path | str) -> Remote | None:
    """The configured remote, or None. Never raises on a corrupt file.

    A hand-edited `remote.json` with a trailing comma should read as "no remote configured",
    which `remote add` can then fix — refusing to run and refusing to be repaired is a state
    with no way out of it.
    """
    path = remote_path(resolve_root(start))
    if not path.is_file():
        return None
    try:
        parsed: Any = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(parsed, dict):
        return None
    fields = cast("dict[str, Any]", parsed)
    if not fields.get("url"):
        return None
    return Remote(url=str(fields["url"]), token=str(fields.get("token", "")),
                  cursor=int(fields.get("cursor", 0) or 0))


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
    current = require_remote(start)
    if cursor > current["cursor"]:
        _write(resolve_root(start), Remote(url=current["url"], token=current["token"],
                                           cursor=int(cursor)))


def _write(root: Path, remote: Remote) -> Remote:
    path = remote_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(handle, "w", encoding="utf-8") as out:
        json.dump(remote, out, indent=2, sort_keys=True)
        out.write("\n")
    # A file that already existed keeps its old mode through O_CREAT, so say it again.
    os.chmod(path, 0o600)
    return remote
