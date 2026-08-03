"""`taskops join <url>` — a teammate becomes part of a board in one command.

Written after watching what joining actually took: `git clone`, then `taskops init`, then
`taskops remote add <url> --token <t>`, then `taskops setup` — four commands, two of which you
have to know exist, one of which needs a token pasted from a chat. Every step after the clone
is derivable from the URL, so every step after the clone is this command's job.

Sharing a board IS sharing a link, which is how every tool people already use does it — nobody
onboards onto a document by configuring a remote. Three links arrive here and `_invitation`
tells them apart: a bare `https://server/board` (you hold a session already, the GitHub case),
`?token=` (the machine credential), and `?invite=` (one person, one use, spent on the way in).

Most of the time there is no link at all: `.taskops/board.json` is committed, so a clone knows
where its board is and `join` takes no argument.

Idempotent, like `init`: joining a board you already joined repairs the wiring (fresh clones
lose their git hooks; `.mcp.json` may be new) and changes nothing else.
"""

from __future__ import annotations

from pathlib import Path

from .._errors import BadRequest
from ._boardfile import write_pointer
from ._invitation import address_of, carried, spend
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


def join(start: Path | str, url: str = "") -> Joined:
    """Init, wire, connect, and pull — everything between a clone and a working board.

    With no URL the repository is asked: `.taskops/board.json` travels with the clone, so the
    second developer types four words and nothing else. That file is written on the way out
    too, so a board joined from a pasted link stops needing the link for everybody after.
    """
    base, token, code = address_of(url or carried(start))
    report = init(start)
    write_pointer(report.root, base)
    if code:
        spend(base, code)       # an invite becomes a session, and `_session` finds it below
    held = token or _session(base)
    already = read_remote(report.root)
    if already is None:
        _signed_in(base, held)
        add_remote(report.root, base, token=token)
    elif already["url"] != base:
        # One board per project is `add_remote`'s rule; joining a DIFFERENT one deserves the
        # same refusal rather than a silent re-point that strands the old board's cursor.
        raise BadRequest(f"this project already syncs with {already['url']} — one board per "
                         f"project; `taskops remote remove` first if you mean to move it")
    if held:
        from .pushpull import pull

        pull(report.root)       # the first cache fill, so `join` ends on a board
    return Joined(root=report.root, url=base, hooks=report.hooks, adopted=report.adopted,
                  needs_login=not held)


def _session(base: str) -> str:
    """This machine's session for that board's server, or "".

    A session is a credential exactly as a token is, and reading it HERE is what stops `join`
    from lying twice: it used to decide both "may I pull" and "does this person need to log in"
    from the token alone, so a signed-in teammate joining a tokenless URL was told to log in —
    right after being let in — and their cache was left empty because the pull was skipped.
    """
    from ._sessionfile import session_for

    return "" if session_for(base) is None else "session"


def _signed_in(base: str, held: str) -> None:
    """Refuse a join with no credential, naming the SERVER to sign in to.

    `add_remote` refuses this too, but its sentence is written for somebody configuring a
    remote by hand: it says "run `taskops login <server-url>`" without knowing which, and the
    obvious guess — the board URL that was just typed — is the one address login rejects. The
    server is the board URL minus its last segment, and it is knowable right here.
    """
    if held:
        return
    server = base.rsplit("/", 1)[0]
    raise BadRequest(f"not signed in to {server}, and this board's URL carries no token.\n\n"
                     f"    taskops login {server}\n\n"
                     f"then run this again — push access to the linked repository is what "
                     f"lets you in, so there is nothing else to ask anybody for")
