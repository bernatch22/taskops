"""WHICH server this command is talking to, and whether this machine may ask it anything.

Split out of `board` when the module hit its budget, and the split names a real seam: every
other line in that command is about a BOARD, and these two are about the machine's relationship
to a SERVER. `create` and `invite` do not come through here at all — one carries a GitHub token
or nothing, the other the board's own credential out of `remote.json` — which is exactly why
the session lookup does not belong in the command that also serves them.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from ....usecases import logins
from ....usecases._sessionfile import bearer_of, session_for
from ._board_render import no_session

__all__ = ["signed_in", "server_of"]


def signed_in(given: str, board_url: str) -> tuple[str, str]:
    host = urlsplit(board_url)
    server = server_of(given) or (f"{host.scheme}://{host.netloc}" if host.netloc
                                              else "")
    held = session_for(server) if server else None
    # An entry with an EMPTY session is a server this machine KNOWS and is not signed in to —
    # written by `remote add <server>` so `board create` needs no `--server`. Treating it as a
    # login sent an empty bearer and turned "you are not signed in" into a bare 401.
    if held is None or not held.get("session"):
        raise no_session(server)
    return server, bearer_of(held["session"])


def server_of(given: str) -> str:
    """The server asked for, else the single one this machine knows.

    Ambiguity is refused rather than guessed: choosing one of two logins on somebody's behalf
    is choosing wrong half the time, and the wrong choice puts a board on a stranger's box.
    """
    known = list(logins())
    return given.strip().rstrip("/") if given else (known[0] if len(known) == 1 else "")
