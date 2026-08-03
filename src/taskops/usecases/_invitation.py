"""Where a joining clone gets its ADDRESS and its CREDENTIAL — the two things it arrives without.

Split from `join` when redeeming an invite pushed that module past its budget, and the line is
not arbitrary: this decides what the caller was given, `join` decides what to do about it. One
reads a URL and a file; the other inits a store, installs hooks, wires a remote and pulls.

Three ways in, and the URL says which:

    …/board                 nothing on it — you are expected to hold a session already
    …/board?token=…         the machine credential, as `serve init` prints it
    …/board?invite=…        one person, one use — redeemed here into a session

The invite is spent HERE rather than by a verb of its own, because the alternative is two steps
and the second one is the one people forget: a spent code and no board.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlunsplit

from .._errors import BadRequest
from ._boardfile import read_pointer

__all__ = ["address_of", "spend", "carried"]


def address_of(url: str) -> tuple[str, str, str]:
    """The board URL as people paste it -> the API base, the token, and the invite on it.

    `?token=` is how the server's own `serve init` prints the address, so the string somebody
    was already sent in a chat is the string this accepts. Anything else on the query is
    dropped deliberately: the remote stores a clean base, and a credential belongs in
    `remote.json` (0600, gitignored) rather than in a URL that lands in shell history.
    """
    parts = urlsplit(url.strip())
    if not parts.scheme or not parts.netloc:
        raise BadRequest(f"`{url}` is not a board URL — it looks like "
                         f"https://server/project (the address the board shows)")
    query = parse_qs(parts.query)
    return (urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", "")),
            (query.get("token") or [""])[0], (query.get("invite") or [""])[0])


def spend(base: str, code: str) -> None:
    """Redeem the invite, so `join` stays the ONE command an invited person runs.

    Single-use by construction, so this runs exactly once per person: a re-run of `join` finds
    the session it already left behind and never reaches here.
    """
    from .boards import redeem_invite

    server, _, board = base.rpartition("/")
    redeem_invite(server, board, code)


def carried(start: Path | str) -> str:
    """The address this clone carries in `.taskops/board.json`, or the way to get one.

    Raising rather than falling back to a prompt: `join` with no argument is a claim that the
    repository knows, and a repository that does not know cannot be rescued by guessing.
    """
    from ..storage import resolve_root

    try:
        found = read_pointer(resolve_root(start))
    except Exception:                          # noqa: BLE001 - not a repository yet
        found = read_pointer(Path(start))
    if not found:
        raise BadRequest(
            "this repository does not say where its board is — `.taskops/board.json` is "
            "missing. Pass the URL once (`taskops join <url>`) and it will be written for "
            "everybody after you, or run `taskops board create` if there is no board yet")
    return found
