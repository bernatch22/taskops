"""The two commands that CONNECT a repo to a board, and the git hooks.

`serve`, `invite` and `ui` — the ones that run a server — live in `serving.py`.
`main.py` only parses and dispatches.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .. import session
from .._json import query
from .._wire import post as post_json
from ..board import DIR, find_root, open_board
from ..store import log
from .._errors import TaskopsError
from ..gitwork import run, bind, remote, install, trailer

# ── the commands ────────────────────────────────────────────────────────────


def init(here: Path) -> int:
    root = find_root(here)
    (root / DIR / "board").mkdir(parents=True, exist_ok=True)
    (root / DIR / "board.json").write_text("{}\n", encoding="utf-8")
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


def join(here: Path, url: str, given: str, key: str = "", discard: bool = False) -> int:
    """Connect this repo to a board — and, with `--key`, register the ssh key that
    will mint every session from here on.

    **It refuses to orphan a local board.** Until this guardrail, joining a repo
    that already had `.taskops/board/` with events in it simply started reading
    the remote one: the local history was still on disk, byte for byte, and
    nothing in taskops would ever look at it again or say so. Nobody was told,
    and the thing that made it invisible was a command about connecting. So a
    local board with events is now a STOP that names both ways out, and
    `--discard-local` archives (never deletes) before proceeding.

    The invite and the PUBKEY travel in the same call: the server burns the invite
    and enrols the key in one act. Then the key signs in ON THE SPOT, which is not
    ceremony — the token an invite mints is a STANDING one, and a clone that kept
    it would never take the refresh path again. What is left in remote.json is a
    SESSION with an expiry, and `session.py` owns it from there.

    Without `--key` this is the join it always was, and the board keeps its
    standing bearer token (milestone rule 3, and the reason the old shape is still
    the default rather than a deprecation).
    """
    root = find_root(here)
    base = url.partition("?")[0]
    _keep_or_archive(root, base, discard)
    params = query(url)
    who = given or actor()
    token, door = params.get("token", ""), {}
    if params.get("invite", ""):
        name = who.partition(":")[2] or "me"
        token, who = redeem(base, params["invite"], name, pubkey(key))
        if key:
            door = {"host": _host_of(base), "principal": name, "key": str(Path(key).expanduser())}
    if not token:
        raise TaskopsError("that URL carries no ?token= or ?invite= — ask for a fresh link")
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


def _wire(root: Path, who: str) -> None:
    """Everything init and join both do — including the ONE git fact the board
    can only learn from the side that has a clone (`gitwork/remote.py`)."""
    install.install_hooks(root, sys.executable)
    install.write_gitignore(root)
    install.write_mcp(root, sys.executable, who)
    install.write_claude_hooks(root, sys.executable)  # delivery only — MENTIONS.md §9
    remote.remember(open_board(root, who), root)


def redeem(base: str, invite: str, who: str, public: str = "") -> tuple[str, str]:
    """Burn an invite, and enrol the key travelling with it. Public because
    `push.py` needs exactly this and only this: a repo with a local board has
    never joined anything, so its first push may also be its first introduction
    to the host — and there must not be two redemptions to keep in step."""
    body: dict[str, str] = {"invite": invite, "who": who}
    if public:
        body["pubkey"] = public
    data = post_json(f"{base.rstrip('/')}/invite/redeem", body, {}, 20.0)
    return str(data.get("token", "")), str(data.get("actor", f"dev:{who}"))


def pubkey(key: str) -> str:
    """The PUBLIC half of `--key`, read from `<key>.pub` — never the private key,
    which never leaves this machine and which `store/pubkeys.py` refuses by name
    if it is ever sent by mistake."""
    if not key:
        return ""
    private = Path(key).expanduser()
    public = private if private.suffix == ".pub" else Path(f"{private}.pub")
    try:
        return public.read_text(encoding="utf-8").strip()
    except OSError as err:
        raise TaskopsError(
            f"cannot read {public} — --key takes the PRIVATE key (the one ssh-keygen signs "
            f"with); its .pub next to it is what gets registered: {err}"
        ) from err


def _host_of(base: str) -> str:
    """The SERVER, out of a board address: `/login` is server scope, not a board's."""
    return base.rstrip("/").rpartition("/")[0]
