"""`taskops join <url>` — a teammate becomes part of a board in one command.

Written after watching what joining actually took: `git clone`, then `taskops init`, then
`taskops remote add <url> --token <t>`, then `taskops setup` — four commands, two of which you
have to know exist, one of which needs a token pasted from a chat. Every step after the clone
is derivable from the URL, so every step after the clone is this command's job.

The URL is the one the board itself shows: `https://server/project?token=…`. Sharing a board IS
sharing that link, which is how every tool people already use does it — nobody onboards onto a
document by configuring a remote. A URL without a token is fine too: that is the GitHub-linked
case, and `login` picks up the credential.

Idempotent, like `init`: joining a board you already joined repairs the wiring (fresh clones
lose their git hooks; `.mcp.json` may be new) and changes nothing else.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlunsplit

from .._errors import BadRequest
from ._autosync import fresh
from .remote import add_remote, read_remote
from .setup import init

__all__ = ["join", "Joined"]


class Joined:
    def __init__(self, *, root: Path, url: str, hooks: list[str], adopted: int,
                 needs_login: bool) -> None:
        self.root = root
        self.url = url
        self.hooks = hooks
        self.adopted = adopted
        self.needs_login = needs_login
        """True when the URL carried no token: the server will want a session, and the render
        tells the person to `taskops login` rather than letting the first pull greet them
        with a 401 they have to interpret."""


def join(start: Path | str, url: str) -> Joined:
    """Init, wire, connect, and pull — everything between a clone and a working board."""
    base, token = _split(url)
    report = init(start)
    already = read_remote(report.root)
    if already is None:
        add_remote(report.root, base, token=token)
    elif already["url"] != base:
        # One board per project is `add_remote`'s rule; joining a DIFFERENT one deserves the
        # same refusal rather than a silent re-point that strands the old board's cursor.
        raise BadRequest(f"this project already syncs with {already['url']} — one board per "
                         f"project; `taskops remote remove` first if you mean to move it")
    if token:
        fresh(report.root)      # the first pull, so `join` ends on a board, not on a promise
    return Joined(root=report.root, url=base, hooks=report.hooks, adopted=report.adopted,
                  needs_login=not token)


def _split(url: str) -> tuple[str, str]:
    """The board URL as people paste it -> the API base and the token riding on it.

    `?token=` is how the server's own `serve init` prints the address, so the string somebody
    was already sent in a chat is the string this accepts. Anything else on the query is
    dropped deliberately: the remote stores a clean base, and a token in `remote.json` (0600,
    gitignored) instead of in a URL that ends up in shell history on every push.
    """
    parts = urlsplit(url.strip())
    if not parts.scheme or not parts.netloc:
        raise BadRequest(f"`{url}` is not a board URL — it looks like "
                         f"https://server/project (the address the board shows)")
    token = (parse_qs(parts.query).get("token") or [""])[0]
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", "")), token
