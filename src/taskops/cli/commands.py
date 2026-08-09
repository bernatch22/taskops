"""The two commands that CONNECT a repo to a board, and the git hooks.

`serve`, `invite` and `ui` — the ones that run a server — live in `serving.py`.
`main.py` only parses and dispatches.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .._json import query
from .._wire import post as post_json
from ..board import DIR, find_root, open_board
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


def join(here: Path, url: str, given: str, key: str = "") -> int:
    """Connect this repo to a board — and, with `--key`, register the ssh key that
    will mint every session from here on.

    The invite and the PUBKEY travel in the same call: the server burns the invite
    and enrols the key in one act, so the token that comes back is the last one
    anybody ever handles. Without `--key` this is the join it always was, and the
    board keeps its standing bearer token (milestone rule 3, and the reason the
    old shape is still the default rather than a deprecation).
    """
    root = find_root(here)
    base = url.partition("?")[0]
    params = query(url)
    who = given or actor()
    token, door = params.get("token", ""), {}
    if params.get("invite", ""):
        name = who.partition(":")[2] or "me"
        token, who = _redeem(base, params["invite"], name, _pubkey(key))
        if key:
            door = {"host": _host_of(base), "principal": name, "key": str(Path(key).expanduser())}
    if not token:
        raise TaskopsError("that URL carries no ?token= or ?invite= — ask for a fresh link")
    install.write_config(root, base.rstrip("/"), token, door or None)
    _wire(root, who)
    print(f"joined {base} as {who}. Hooks installed; the board is in MCP.")
    if door:
        print(f"  and {door['key']} signs you in from now on — no token to copy again")
    return 0


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


def _redeem(base: str, invite: str, who: str, pubkey: str = "") -> tuple[str, str]:
    body: dict[str, str] = {"invite": invite, "who": who}
    if pubkey:
        body["pubkey"] = pubkey
    data = post_json(f"{base.rstrip('/')}/invite/redeem", body, {}, 20.0)
    return str(data.get("token", "")), str(data.get("actor", f"dev:{who}"))


def _pubkey(key: str) -> str:
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
