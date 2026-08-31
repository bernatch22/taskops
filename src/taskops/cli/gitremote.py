"""`taskops remote git` — this checkout's git, pointed at the board's own repo.

    taskops remote git                  print the address and the two lines to paste
    taskops remote git --add            wire them here (remote `taskops`, no origin touched)
    taskops remote git <host>/<board>   another board's address, explicitly

§16, "The host becomes the remote", left one thing on the DEV's side unsaid: the
host serves `https://<host>/<board>/repo.git` and nothing in the CLI spelled that
address out loud, so the only way to reach it was to read `http/gitpack.py`. This
command is that sentence, and it is the same act as `taskops remote add` —
recording an address — so it stays on that verb rather than becoming a twelfth
command.

**`origin` is never written, and `--name origin` is REFUSED** — not "left alone
if it exists": refused outright. A checkout's `origin` is somebody's working
setup, very often their GitHub, and no state of it is this command's to decide,
its absence included. So the remote is `taskops`, `--name <other>` when even
that is taken, and a name in use is a refusal naming that flag instead of a
`set-url`. Adding a remote is CONNECTING; repointing an `origin` is managing.

**The credential is a HELPER, never a URL.** The obvious spelling —
`https://x:<token>@host/<board>/repo.git` — is refused here, and not on taste:
`git remote add` writes its URL into `.git/config`, plaintext with the repo's
own permissions, so that spelling persists a live session token in the one file
nobody thinks to look at. It is also WRONG within the hour, because a taskops
session expires (`session.py`) and a token baked into a config cannot renew
itself. So what gets configured is `credential.<host>.helper`, and the helper is
this CLI: git asks for the password at push time, `credential()` below mints or
renews a session from the ssh key already on disk (`identity.establish`, the
same one every board verb uses), hands git the token on a pipe, and NOTHING is
written. One credential story, §19's, through git's own door.

**Where the address is SPELLED, and where it is not.** This command prints the
exact URL for one board; `board ls` prints the shape (`shape`, below). The board
PAYLOAD gains no `repo_url`: the server cannot know its own public address (a
proxy, a port-forward, the local `taskops ui` window — every reader reached it
at an address the server never saw), so a stored one rots first and sends a dev
to the wrong host. The address is (the host you asked) + `/<board>/repo.git`, a
derivation the CLIENT can always do right and the server never can.
"""

from __future__ import annotations

import sys
import argparse
from pathlib import Path

from . import commands
from .. import identity
from ..board import find_root, read_config
from .remote import named, recorded_host
from .._errors import TaskopsError
from ..gitwork import run

REMOTE = "taskops"
"""The name added by `--add` — never `origin`, and never a fork's `upstream`:
the two names git culture has already spent."""

USERNAME = "x"
"""Basic wants a username and the token is the whole credential, so the field is
decoration — the same `x` `http/gitpack.py` documents on its side."""

SUFFIX = "repo.git"  # `http/routes.py`'s own first segment, spelled once here

NOT_ORIGIN = (
    "`origin` is git's and this command does not take it over — that remote is "
    "somebody's own setup (very often their GitHub), and repointing it is not "
    "connecting, it is rewriting. The default name works: taskops remote git --add"
)

TAKEN = (
    "this checkout already has a remote called {name}, pointing at {url} — "
    "`taskops remote git --add --name <other>` adds one under a name that is free. "
    "Nothing here rewrites a remote you configured."
)

HELPER_TAKEN = (
    "a credential helper for {host} is already configured here ({have}) — leave it, "
    "or replace it yourself with `git config --local credential.{host}.helper …`. "
    "This command does not overwrite a credential you set up."
)


def url_for(host: str, board: str) -> str:
    """`https://<host>/<board>/repo.git` — spelled ONCE on the client side."""
    return f"{host.rstrip('/')}/{board}/{SUFFIX}"


def shape(host: str) -> str:
    """What `board ls` says about where the git lives — the SHAPE, on the line it
    already prints, once. Not per row: the address is the same derivation for
    every board on the host, and repeating it N times is noise, not discovery."""
    return f"   ·   git: {host.rstrip('/')}/<board>/{SUFFIX} (taskops remote git)"


def helper_command(python: str) -> str:
    """What git runs to get the password. `!` is git's own marker for "this is a
    shell command, not a `git-credential-<name>` on PATH", and the interpreter is
    named absolutely for `gitwork/install.py`'s reason: the hooks git fires do not
    inherit whatever virtualenv was active when this was configured."""
    return f'!"{python}" -m taskops.cli hook credential'


def wire(args: argparse.Namespace, python: str) -> int:
    """`taskops remote git [--add] [--name <n>]` — print it, or write it."""
    root = find_root(Path.cwd())
    host, board = named(str(args.url))
    url, name = url_for(host, board), str(getattr(args, "name", "") or REMOTE)
    helper = helper_command(python)
    if name == "origin":
        raise TaskopsError(NOT_ORIGIN)
    if not bool(getattr(args, "add", False)):
        print(url)
        print(f"  git remote add {name} {url}")
        print(f"  git config --local credential.{host}.helper '{helper}'")
        print(f"  git push {name} <branch>   — your ssh key mints the token, nothing to type")
        print("  or write both here:  taskops remote git --add")
        return 0
    _remote(root, name, url)
    _helper(root, host, helper)
    print(f"{name}  {url}")
    print(f"  credential.{host}.helper mints a session from your ssh key at push time")
    print(f"  no token is written anywhere — git push {name} <branch>")
    return 0


def _remote(root: Path, name: str, url: str) -> None:
    """Add it, or refuse. `git remote add` would refuse a duplicate itself, and
    the refusal is intercepted here so it names the flag that gets past it."""
    have = run.git("remote", "get-url", name, cwd=root)
    if have.ok and have.out.strip():
        if have.out.strip() == url:
            return  # already exactly this: re-running is free and says so
        raise TaskopsError(TAKEN.format(name=name, url=have.out.strip()))
    run.must("remote", "add", name, url, cwd=root, why=f"cannot add the remote {name}")


def _helper(root: Path, host: str, helper: str) -> None:
    """Configure the helper for THIS host only: `credential.<url>` answers for
    that URL and nothing else, which is exactly the scope of the token it hands
    out (`session.py` mints per host)."""
    have = run.git("config", "--local", "--get", f"credential.{host}.helper", cwd=root)
    if have.ok and have.out.strip():
        if have.out.strip() == helper:
            return
        raise TaskopsError(HELPER_TAKEN.format(host=host, have=have.out.strip()))
    run.must(
        "config", "--local", f"credential.{host}.helper", helper,
        cwd=root, why=f"cannot configure the credential helper for {host}",
    )


def credential(text: str, rest: list[str]) -> int:
    """git's credential helper, answering `get` and only `get`.

    Protocol (`gitcredentials(7)`): the operation arrives as argv, the request as
    `key=value` lines on stdin, the answer as `key=value` lines on stdout. An
    unanswered request is not an error — git moves to the next helper — so every
    reason to decline is silence, plus a line on stderr when it is a FAILURE:
    `hooks.py`'s policy, for its reason. `store` and `erase` are declined too: a
    helper that caches is a helper that persists a token, and minting is free.

    It also declines a host that is not the one this checkout operates — the
    second wall, and the one that matters: a checkout whose recorded host changed
    must not sign a challenge to the old one.
    """
    if (rest[0] if rest else "get") != "get":
        return 0  # store / erase: nothing is cached, so there is nothing to do
    asked = _fields(text)
    wanted = f"{asked.get('protocol', '')}://{asked.get('host', '')}"
    known = recorded_host()
    if not known or wanted != known.rstrip("/"):
        return 0
    root = find_root(Path.cwd())
    config = read_config(root)
    try:
        token, door = identity.establish(root, known, config, "", "", commands.principal())
    except TaskopsError as err:
        print(f"taskops: {err}", file=sys.stderr)
        return 0
    if door and identity.is_own_host(config, known):
        identity.cache_login(root, door)
    print(f"username={USERNAME}")
    print(f"password={token}")
    return 0


def _fields(text: str) -> dict[str, str]:
    """git's request, as a dict. A blank line ends it; anything unparseable is
    dropped rather than guessed at."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            break
        key, sep, value = line.partition("=")
        if sep:
            out[key.strip()] = value.strip()
    return out
