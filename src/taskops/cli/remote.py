"""`taskops remote add <url>` — the host this checkout operates, recorded ONCE.

    taskops remote add https://taskops.example.com     record it, like git's origin
    taskops remote                                     print what is recorded

Git asks for neither a URL nor an identity file on every push, and the two
reasons it does not are both copied here: the address is recorded per CLONE
(`.git/config`, uncommitted — here `.taskops/remote.json`, the private,
per-machine file `join --key` and `board push --key` already cache the same
`login.host` into), and the key is DISCOVERED (`identity.discover_key`, ssh's own
identity files in ssh's own order). With both, every operate verb goes bare.

**This is NOT the host alias registry `operate.py` refuses, and the difference is
the whole point.** What was refused there is a TABLE — many names, global, a
third place a server's address lives and the first to drift. This is ONE host,
in the ONE file that already holds it, written by an explicit command instead of
only as a side effect of a `join` the owner on day one cannot run. Recording an
address is not signing in: nothing is minted here and no key is touched.

The BOARD's name is recorded beside it, by `board create`, in the same `login`
block: the host and the board are one fact — the address — and `_locate.py`
merges that block field by field so a later sign-in cannot drop it. Without it,
`board create minombre` followed by a bare `board push` would re-derive the
DIRECTORY name, find no such board, and make the human repeat a name they had
already chosen.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import identity
from .._json import as_object
from ..board import find_root, read_config
from .._errors import TaskopsError
from .._locate import write_remote

NO_REMOTE = "no remote recorded here — taskops remote add https://<host>"

NO_HOST = (
    "which host? Record it once, git style: `taskops remote add https://<host>` — or "
    "pass --host https://<host>, or run this in a checkout joined to one with "
    "`taskops join <url> --key ~/.ssh/id_ed25519` (a join records it too)"
)

BAD_URL = (
    "{url} is not a host URL — taskops remote add https://<host> (the scheme is how a "
    "URL is told from a board name, so it is required)"
)

ALREADY = (
    "this checkout already operates {known} — `taskops remote add {url} --replace` if "
    "that is the move. Where a board lives is a decision, not a typo, and every bare "
    "`board push` / `board create` after this points at whatever is recorded here."
)


def remote(args: argparse.Namespace) -> int:
    """`add` records the host; no argument prints it, `git remote -v` style."""
    root = find_root(Path.cwd())
    url, known = str(args.url), recorded_host()
    if str(args.action) != "add":
        print(f"origin  {known}" if known else NO_REMOTE)
        return 0
    host = _host(url)
    if known and known.rstrip("/") != host and not bool(args.replace):
        raise TaskopsError(ALREADY.format(known=known, url=url))
    write_remote(root, {"login": {"host": host}})
    print(f"origin  {host}")
    print(f"  taskops board create [{default_board(root)}]   ·   taskops board push")
    return 0


def address(target: str) -> tuple[str, str]:
    """`<host>/<name>`, `<host>`, `<name>` or nothing — into (host, name).

    A URL is recognised by its scheme and never by counting slashes: `https://h/b`
    has three and `h/b` has one, and guessing between them is how a board called
    `https:` gets created."""
    text = target.strip().rstrip("/")
    if "://" in text:
        base, _, name = text.rpartition("/")
        return (text, "") if base.endswith(":/") else (base, name)
    host = recorded_host()
    if not host:
        raise TaskopsError(NO_HOST)
    return host, text


def named(target: str) -> tuple[str, str]:
    """`address`, plus the default for a board nobody named on the command line.

    Explicit argument > the name `board create` recorded > the directory. The
    verbs that act ON one board share this so the precedence is decided once —
    `board create`, `board visibility` (`operate.py`) and `board push`."""
    host, name = address(target)
    return host, name or default_board(find_root(Path.cwd()))


def _host(url: str) -> str:
    """A host URL, recognised by its scheme — `address` above applies the same
    rule for the same reason, and this is where a typo is caught EARLY: recording
    a bad address that only fails on the next verb is the worse order."""
    text = url.strip().rstrip("/")
    if not text.startswith(("http://", "https://")):
        raise TaskopsError(BAD_URL.format(url=url or "«nothing»"))
    return text


def recorded_host() -> str:
    """The server this checkout operates: what `remote add` wrote, or what the
    `join --key` that registered the key wrote — the same field, either way."""
    return str(_login().get("host", ""))


def default_board(root: Path) -> str:
    """Which board a bare `board create` / `push` / `visibility` is about.

    Precedence, and it is the point of the amendment: the RECORDED name (what
    `board create` chose) beats the directory, which is only the first guess —
    `gh repo create`'s convention, and it is a default rather than a rule
    because a checkout is very often named after its board and never must be."""
    return str(_login().get("board", "")) or root.name


def record_board(root: Path, host: str, name: str) -> None:
    """Remember the name `board create` actually made, so nobody types it twice.

    Only when `host` is the one this checkout operates — creating a board on a
    DIFFERENT server from inside a joined checkout is legitimate and must leave
    this file alone, the same rule `identity.is_own_host` holds the token to.
    Without the guard the next bare `board push` here would aim at a board on a
    server this checkout has nothing to do with (caught by
    `test_operating_another_host_leaves_this_checkouts_own_session_alone`)."""
    if identity.is_own_host(read_config(root), host):
        write_remote(root, {"login": {"board": name}})


def _login() -> dict[str, object]:
    return as_object(read_config(find_root(Path.cwd())).get("login"))
