"""The sessions a GitHub login mints, and the file they live in.

A session is the ONLY thing a GitHub login leaves behind: a random hex string, the account
it belongs to, the projects it opens and when it was made. The GitHub token that proved all
of that is never here — see `accounts` for why it cannot be, and the test that pins it.

**`<root>/.sessions.json`, `0600`, and the leading dot is load-bearing.** A project name is
`[a-z0-9-]` (`transports.http.projects.NAME`), so a name beginning with a dot is refused as
syntax — which means this file can never be shadowed by, or mistaken for, a project. It sits
in the server root rather than in one project because a session spans several of them.

**Expiry is checked on READ and applied on WRITE.** There is no sweeper and no daemon: a
stale entry is invisible the moment it is old enough, and it leaves the disk the next time
anybody logs in. That ordering is what makes "an expired session is refused" true even on a
server that has not been written to in a month.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any, cast

from .._clock import now

__all__ = ["SESSIONS_FILE", "TTL", "mint", "resolve"]

SESSIONS_FILE = ".sessions.json"

TTL = 7 * 24 * 3600.0
"""A week. Long enough that a person logs in about as often as they think about it, short
enough that a session copied off a laptop stops working without anybody having to notice."""

BYTES = 16
"""128 bits, hex-encoded — the 32 characters the wire contract declares."""


def mint(root: Path, login: str, projects: list[str]) -> str:
    """A new session for `login` over `projects`. Writing it prunes the expired ones."""
    session = secrets.token_hex(BYTES)
    live = _read(root)
    live[session] = {"login": login, "projects": list(projects), "created": now()}
    _write(root, live)
    return session


def resolve(root: Path, session: str) -> dict[str, Any] | None:
    """`{login, projects, created}`, or None when it is unknown OR expired — one answer for
    both, because telling them apart would say whether a guessed string ever existed."""
    if not session:
        return None
    return _read(root).get(session)


def opens(root: Path, session: str, project: str) -> bool:
    """Whether that session may enter that project. The list is the whole authorisation."""
    found = resolve(root, session)
    return bool(found) and project in cast("list[str]", (found or {}).get("projects") or [])


def _read(root: Path) -> dict[str, dict[str, Any]]:
    """The live entries. A missing or corrupt file is an empty one, never an exception: this
    is read on the way into every request, and a stray byte must fail closed, not 500."""
    try:
        raw = (root / SESSIONS_FILE).read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        parsed: Any = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    at = now()
    entries: dict[str, Any] = cast("dict[str, Any]", parsed)
    live: dict[str, dict[str, Any]] = {key: cast("dict[str, Any]", value)
                                       for key, value in entries.items()
                                       if isinstance(value, dict)}
    return {key: entry for key, entry in live.items() if at - _created(entry) < TTL}


def _created(entry: dict[str, Any]) -> float:
    try:
        return float(entry.get("created", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _write(root: Path, live: dict[str, dict[str, Any]]) -> None:
    """`touch(0o600)` BEFORE the write, so the file never exists — not for the microsecond
    between create and chmod — with the umask's permissions. Same rule as the project token."""
    path = root / SESSIONS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600, exist_ok=True)
    path.write_text(json.dumps(live, indent=1), encoding="utf-8")
