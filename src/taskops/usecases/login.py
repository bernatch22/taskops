"""`taskops login` — trade a GitHub token for a session, once per machine per server.

The problem this solves is the sentence "and issues each developer a token". Somebody had to
mint a secret, deliver it over a channel that is usually chat, and rotate it by hand when a
person left. A team already agrees on who is on it — that agreement lives in the GitHub repos
the server's projects point at — so the server can ask GitHub instead of asking an admin.

**The GitHub token is not ours to keep.** It arrives from `gh auth token` or a hidden prompt,
crosses one HTTPS call, and the function returns; it is never written, never logged, never
echoed. What we store is the session the server issued back, which is scoped to that server,
expires on its own in seven days, and can be dropped from either end. That asymmetry is the
whole security argument for this design: a stolen `sessions.json` costs one server for one
week, a stolen GitHub token costs every repository the person can reach, forever.

The wire shape is frozen (a sibling module serves it):

    POST <base>/api/auth/github  {"github_token": …} → {"login", "session", "projects": [name]}

`login` returns the project NAMES because the caller's next move is printing one
`taskops remote add <base>/<name>` line per project, and a name is what that line needs.
"""

from __future__ import annotations

from typing import Any, cast

from .._errors import TaskopsError
from ._sessionfile import drop_session, is_session, load_sessions, save_session, session_for
from ._wireclient import Wire

__all__ = ["login", "logout", "session_of", "logins", "is_session"]


def login(url: str, github_token: str) -> dict[str, Any]:
    """Sign in and remember the session. Returns `{url, login, projects}` — never the session.

    A 403 or a 502 leaves this as the server's own sentence, raised by the wire: it is the
    only text that knows WHY GitHub said no (not a member, token without `repo`, GitHub
    itself down), and inventing a second sentence here would hide it.
    """
    base = _base(url)
    if not github_token.strip():
        raise TaskopsError("no GitHub token — `gh auth login`, or paste one with the `repo` "
                           "scope when asked")
    answer = Wire(base, "").call("POST", "/api/auth/github",
                                 body={"github_token": github_token.strip()})
    session = str(answer.get("session") or "")
    who = str(answer.get("login") or "")
    if not session:
        raise TaskopsError(f"{base} accepted the GitHub token but issued no session — that "
                           f"server is not speaking the auth contract")
    save_session(base, session, who)
    return {"url": base, "login": who, "projects": _names(answer.get("projects"))}


def logout(url: str) -> str:
    """Forget one server's session. The server's copy expires on its own."""
    base = _base(url)
    if not drop_session(base):
        raise TaskopsError(f"not signed in to {base} — nothing to forget")
    return base


def session_of(url: str) -> dict[str, str]:
    """The stored session for a server, for the ONE caller that must show it: pasting it
    into the UI's unlock screen. Every other reader gets the login and the projects."""
    found = session_for(_base(url))
    if found is None:
        raise TaskopsError(f"not signed in to {_base(url)} — run `taskops login {_base(url)}`")
    return found


def logins() -> dict[str, dict[str, str]]:
    """Every server this machine is signed in to, sessions included — callers print the
    `login` field and nothing else unless the person asked."""
    return load_sessions()


def _base(url: str) -> str:
    address = url.strip().rstrip("/")
    if not address.startswith(("http://", "https://")):
        raise TaskopsError(f"`{url}` is not a server address — pass the base URL, like "
                           f"https://taskops.example.com")
    return address


def _names(projects: Any) -> list[str]:
    """The contract says a list of names; a server that grew richer rows still works, because
    a client that crashed on an ADDED field would make the contract impossible to extend."""
    if not isinstance(projects, list):
        return []
    found: list[str] = []
    for row in cast("list[Any]", projects):
        name: Any = cast("dict[str, Any]", row).get("name") if isinstance(row, dict) else row
        if name:
            found.append(str(name))
    return sorted(found)
