"""The two commands that CONNECT a repo to a board, and the git hooks.

`serve`, `invite` and `ui` — the ones that run a server — live in `serving.py`.
`main.py` only parses and dispatches.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import enrol, watch
from .. import session, identity
from .._json import query
from ..board import DIR, find_root, open_board
from ..store import log
from .._errors import TaskopsError
from ..gitwork import run, bind, remote, install, trailer, claudefiles

# ── the commands ────────────────────────────────────────────────────────────


def init(here: Path) -> int:
    root = find_root(here)
    (root / DIR / "board").mkdir(parents=True, exist_ok=True)
    install.write_local(root)
    _wire(root, actor())
    print(f"local board in {root / DIR / 'board'} — the MCP tools are the way in")
    return 0


ORPHAN = (
    "there is a LOCAL board in {path} with {n} event(s) in it, and joining {url} would "
    "make it invisible from this repo forever — every card, comment and commit in it. "
    "Two ways forward, and both are explicit:\n"
    "  taskops board push {url}   take the history along — it becomes the hosted board\n"
    "  taskops join … --discard-local   archive it beside itself and join anyway\n"
    "(--discard-local renames the directory; nothing is ever deleted.)"
)


def join(
    here: Path, target: str, given: str, key: str = "", discard: bool = False, invite: str = ""
) -> int:
    """Connect this repo to a board. Bare like every other verb since the host is
    recorded and the key is discovered:

        taskops remote add https://host:8787        once per checkout
        taskops join my-project                     registered key: signs in, done
        taskops join my-project --invite <id>       first time: enrols the key too
        taskops join my-project                     no key anywhere + public board: read-only

    The name defaults exactly as `board create`'s does (recorded name, else the
    directory), `<host>/<name>` is the explicit form, and the full URL — with
    `?token=` or `?invite=` — keeps working unchanged, because production's four
    boards were joined that way and their links must not rot (milestone rule 3).

    **It refuses to orphan a local board.** Until this guardrail, joining a repo
    that already had `.taskops/board/` with events in it simply started reading
    the remote one: the local history was still on disk, byte for byte, and
    nothing in taskops would ever look at it again or say so. So a local board
    with events is a STOP that names both ways out, and `--discard-local`
    archives (never deletes) before proceeding.

    With an invite, the invite and the PUBKEY travel in the same call: the server
    burns the invite and enrols the key in one act. Either way the key then signs
    in ON THE SPOT and what lands in remote.json is a SESSION with an expiry —
    never a standing token to copy around. Keys exist so tokens do not travel.
    """
    from . import remote as remote_cli

    root = find_root(here)
    bare = "://" not in target
    if bare:
        host, name = remote_cli.named(target)
        target = f"{host}/{name}"
    base = target.partition("?")[0]
    _keep_or_archive(root, base, discard)
    params = query(target)
    invite = invite or params.get("invite", "")
    who = given or actor()
    name = who.partition(":")[2] or "me"
    found = Path(key).expanduser() if key else identity.discover_key()
    token, door = params.get("token", ""), {}
    if invite:
        token, who = enrol.redeem(base, invite, name, enrol.pubkey(str(found) if found else ""))
        if found:
            door = {"host": enrol.host_of(base), "principal": name, "key": str(found)}
    elif bare and found:
        # No invite and no token: the KEY is the whole credential. Proved against
        # the host BEFORE anything is written — a refused sign-in must not leave
        # a half-joined checkout behind (`cache=False`: nothing lands on disk).
        door = {"host": enrol.host_of(base), "principal": name, "key": str(found)}
        session.sign_in(root, door["host"], door["principal"], found, cache=False)
        who = f"dev:{name}"
    if not token and not door:
        # No credential at all — a PUBLIC board is joined read-only (`watch.py`).
        return watch.watch(root, base.rstrip("/"))
    install.write_config(root, base.rstrip("/"), token, door or None)
    if door:
        session.sign_in(root, door["host"], door["principal"], Path(door["key"]))
    _wire(root, who)
    print(f"joined {base} as {who}. Hooks installed; the board is in MCP.")
    if door:
        print(f"  and {door['key']} signs you in from now on — no token to copy again")
    return 0


def _keep_or_archive(root: Path, url: str, discard: bool) -> None:
    """The guardrail, before anything is written. The count comes from the LOG
    and not from the directory's existence: `taskops init` leaves an empty board
    behind, and refusing on that would make the ordinary init-then-join sequence
    impossible for no gain — an empty history has nothing to orphan."""
    from .push import archive  # the same rename `board push` does at its step 5

    local = root / DIR / "board"
    events, _ = log.read(local / "events.jsonl")
    if not events:
        return
    if not discard:
        raise TaskopsError(ORPHAN.format(path=local, n=len(events), url=url))
    print(f"  the local board ({len(events)} events) is archived at {archive(local)}")


def hook(here: Path, which: str, rest: list[str]) -> int:
    """The two GIT hooks; `hook claude` is routed in `main` and never prints.

    Neither of these may block a commit. Failures print and return 0.
    """
    root = find_root(here)
    if which == "trailer":
        if rest:
            trailer.stamp_file(Path(rest[0]), run.branch_at(here))
        return 0
    facts = bind.commit_facts(here)
    if facts is None:
        return 0
    try:
        board = open_board(root, actor())
        bind.record(board, root, facts)
        bind.drain(board, root)
    except TaskopsError as err:
        print(f"taskops: {err}", file=sys.stderr)  # visible, never swallowed
    bind.push_card(here, str(facts["branch"]))
    return 0


# ── plumbing ────────────────────────────────────────────────────────────────


def actor() -> str:
    """`TASKOPS_ACTOR` wins — that is how a spawned worker knows who it is."""
    return os.environ.get("TASKOPS_ACTOR") or f"dev:{os.environ.get('USER', 'me')}"


def principal() -> str:
    """The bare NAME inside `actor()` — `dev:berna` → `berna`. That is what a
    host knows you as: a principal is registered against a key, not an actor
    string. It is a guess from the environment and `--as` overrides it."""
    return actor().partition(":")[2]


def _wire(root: Path, who: str) -> None:
    """Everything init and join both do — including the ONE git fact the board
    can only learn from the side that has a clone (`gitwork/remote.py`)."""
    install.install_hooks(root, sys.executable)
    install.write_gitignore(root)
    claudefiles.write_mcp(root, sys.executable, who)
    claudefiles.write_claude_hooks(root, sys.executable)  # delivery only
    remote.remember(open_board(root, who), root)


