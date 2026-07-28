"""`~/.taskops/sessions.json` — who this MACHINE is on each taskops server.

Deliberately NOT inside any repository. A project's `remote.json` is per-project because the
token in it is per-project; a login is per-PERSON, and one developer works ten checkouts of
three repositories. Writing the session into each of them would mean logging in ten times and
rotating ten copies, and the one that got missed would be in whichever clone nobody opened.
The home directory is also the only place `taskops init`'s gitignore cannot protect: a file
that never enters a work tree can never enter a commit.

Same 0600-at-creation mechanics as `_remotefile`, for the same reason — a `write_text`
followed by `chmod` publishes the secret to every account on the machine for one syscall.

The stored credential is written into `remote.json` with a `session:` prefix so that the
shape of what is on disk says which kind of secret it is: `push` needs to know, because a
401 on a project token means "your token is wrong" and a 401 on a session means "log in
again", and those are different sentences for the person reading them. The prefix is a LOCAL
marker only — the wire sends the bare session, which is what the frozen contract specifies.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

__all__ = ["SESSION_PREFIX", "sessions_path", "load_sessions", "save_session", "drop_session",
           "session_for", "as_credential", "is_session", "bearer_of", "expired"]

SESSION_PREFIX = "session:"


def sessions_path() -> Path:
    """`$TASKOPS_HOME/.taskops/sessions.json`, defaulting to the real home.

    The override exists so a test never writes to the developer's own file — and so a
    shared build agent can point several checkouts at one scratch home."""
    home = os.environ.get("TASKOPS_HOME") or Path.home()
    return Path(home) / ".taskops" / "sessions.json"


def load_sessions() -> dict[str, dict[str, str]]:
    """Every server this machine is signed in to. A corrupt file reads as none — the same
    call that could refuse to run is the one that would then refuse to be repaired."""
    path = sessions_path()
    if not path.is_file():
        return {}
    try:
        parsed: Any = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    found: dict[str, dict[str, str]] = {}
    for url, row in cast("dict[str, Any]", parsed).items():
        if isinstance(row, dict):
            fields = cast("dict[str, Any]", row)
            found[str(url)] = {str(key): str(value) for key, value in fields.items()}
    return found


def save_session(url: str, session: str, login: str) -> None:
    """One entry per server. Logging in to a second one never touches the first."""
    held = load_sessions()
    held[url.rstrip("/")] = {"session": session, "login": login}
    _write(held)


def drop_session(url: str) -> bool:
    """Forget one server. False when there was nothing to forget."""
    held = load_sessions()
    if held.pop(url.rstrip("/"), None) is None:
        return False
    _write(held)
    return True


def session_for(url: str) -> dict[str, str] | None:
    """The session covering `url`, matched by PREFIX and longest first.

    `remote add` is given `<server>/<project>`, so an exact match would never fire; longest
    first is what keeps a login to `https://host/team-a` from answering for `https://host`.
    """
    address = url.rstrip("/")
    held = load_sessions()
    for base in sorted(held, key=len, reverse=True):
        if address == base or address.startswith(base + "/"):
            return {**held[base], "url": base}
    return None


def as_credential(session: str) -> str:
    return SESSION_PREFIX + session


def is_session(credential: str) -> bool:
    return credential.startswith(SESSION_PREFIX)


def bearer_of(credential: str) -> str:
    """What actually goes on the wire. The contract says `Bearer <session>`; the prefix is
    ours and stops at this line."""
    return credential[len(SESSION_PREFIX):] if is_session(credential) else credential


def expired(base: str, credential: str) -> str | None:
    """The sentence a 401 deserves when the credential was a session, else None.

    A session lasts seven days on the server side, so this 401 is the ordinary end of a week
    rather than a misconfiguration, and the answer is one command.
    """
    if not is_session(credential):
        return None
    found = session_for(base)
    where = found["url"] if found else base
    return (f"the session for {where} expired — run `taskops login {where}` again "
            f"and this project keeps working")


def _write(sessions: dict[str, dict[str, str]]) -> None:
    path = sessions_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(handle, "w", encoding="utf-8") as out:
        json.dump(sessions, out, indent=2, sort_keys=True)
        out.write("\n")
    os.chmod(path, 0o600)     # O_CREAT leaves an existing file's mode alone.
