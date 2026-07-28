"""Reading and writing `.taskops/remote.json` — the file mechanics, nothing else.

Split from `remote` by what each half is: that module decides WHAT a remote is (one per
project, a URL and a secret, two cursors that never compare), this one knows how to put it
on disk without leaking it. The file is written through `os.open` with mode 0600 rather than
`write_text` followed by a `chmod`, because the two-step version publishes the token to every
user on the machine for the width of one syscall.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

from ..contracts import Remote
from ..storage import PROJECT_DIR, resolve_root

__all__ = ["REMOTE_FILE", "remote_path", "load", "write"]

REMOTE_FILE = f"{PROJECT_DIR}/remote.json"


def remote_path(root: Path) -> Path:
    return root / REMOTE_FILE


def load(start: Path | str) -> Remote | None:
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
                  pushed=int(fields.get("pushed", 0) or 0),
                  cursor=int(fields.get("cursor", 0) or 0))


def write(root: Path, remote: Remote) -> Remote:
    path = remote_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(handle, "w", encoding="utf-8") as out:
        json.dump(remote, out, indent=2, sort_keys=True)
        out.write("\n")
    # A file that already existed keeps its old mode through O_CREAT, so say it again.
    os.chmod(path, 0o600)
    return remote
