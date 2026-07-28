"""The URL to open in a browser, credential included.

A board behind a credential is a board somebody has to assemble a URL for, and the assembly is
exactly the part a person gets wrong: the right host, the right project, and a secret that is
either a session in the home directory or a token in the project. This is that assembly, once.

The credential goes in the QUERY rather than being left to the access screen, because the point
of the command is that the board OPENS — a screen asking to paste something the caller already
has is a step that exists only because nobody wrote this function. What goes on the wire is
`bearer_of`, never the stored form: the `session:` prefix is a local marker and the server has
never heard of it.
"""

from __future__ import annotations

from pathlib import Path

from .._errors import NotInitialized
from ._sessionfile import bearer_of, is_session, load_sessions, session_for
from .remote import read_remote

__all__ = ["board_url", "root_url"]


def board_url(start: Path | str) -> str:
    """The board of the project you are standing in, ready to open.

    The project's own credential first: a machine token opens exactly this board and is what
    the project was configured with. When that credential IS a session, the stored one wins —
    a later `taskops login` refreshes the home directory and never walks the checkouts, so
    trusting the copy in the project would open boards with last week's session.
    """
    remote = read_remote(start)
    if remote is None:
        raise NotInitialized(
            "this project has no remote — run `taskops remote add <url>/<project>` first, or "
            "open the local board with `taskops ui`")
    credential = remote["token"]
    if is_session(credential) or not credential:
        found = session_for(remote["url"])
        credential = found["session"] if found else credential
    return _with(remote["url"], credential)


def root_url(url: str = "") -> tuple[str, dict[str, str]]:
    """The server's own page — every board the session can reach — and who it thinks you are.

    With no argument it picks the one server this machine has signed in to, and refuses to
    guess between several: opening another team's board is a worse outcome than one more word
    on the command line.
    """
    if url:
        found = session_for(url)
        if found is None:
            raise NotInitialized(f"not signed in to {url} — run `taskops login {url}`")
        return _with(found["url"], found["session"]), found
    known = load_sessions()
    if not known:
        raise NotInitialized("not signed in anywhere — run `taskops login <url>` first")
    if len(known) > 1:
        servers = ", ".join(sorted(known))
        raise NotInitialized(f"signed in to several servers ({servers}) — name the one you "
                             f"mean, e.g. `taskops open --server {sorted(known)[0]}`")
    base = next(iter(known))
    found = {**known[base], "url": base}
    return _with(base, found["session"]), found


def _with(base: str, credential: str) -> str:
    """The address plus the credential, or the address alone.

    Alone is not a failure: the access screen is a working way in, and a URL that opens onto a
    prompt beats a command that refuses because it could not find a secret.
    """
    address = base.rstrip("/") + "/"
    return f"{address}?token={bearer_of(credential)}" if credential else address
