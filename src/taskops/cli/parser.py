"""Every flag the CLI accepts, and nothing about what any of them DO.

Split off `main.py` when two chapters landed in the same week — `board pull`/`rm`
and `board forge` — and pushed one module past the 200-line budget together. The
seam is the one that was already there: `main.py` had exactly two functions, one
that DESCRIBES the surface and one that DISPATCHES it, and only the first grows
when a command gains a flag. So `main.py` is now the dispatch table and reads as
one, and this file is the surface.

The description is passed IN rather than read from a docstring here: the help a
human sees at `taskops --help` is `main.py`'s docstring — the list of commands,
which belongs beside the dispatch that proves it complete — and importing it
back the other way would be the cycle.
"""

from __future__ import annotations

import argparse

from . import gitremote
from ..core import forge

AS_HELP = "the principal that key belongs to (default: $USER)"


def build(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="taskops", description=description)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="a local board in this repo")
    _join(sub)
    origin = sub.add_parser("remote", help="the host this checkout operates (git's origin)")
    origin.add_argument("action", nargs="?", default="", choices=["", "add", "git"])
    # `add` takes the HOST; `git` takes an optional <host>/<board> and otherwise
    # uses the recorded pair — one slot, because both are an address.
    origin.add_argument("url", nargs="?", default="", help="add: https://<host> · git: <host>/<board>")
    origin.add_argument(
        "--replace", action="store_true", help="this checkout already names another host"
    )
    origin.add_argument(
        "--add",
        action="store_true",
        help="remote git: write the remote and the credential helper here instead of printing them",
    )
    origin.add_argument(
        "--name",
        default="",
        help=f"remote git --add: the remote's name (default: {gitremote.REMOTE}; never origin)",
    )
    server = sub.add_parser("serve", help="host boards")
    server.add_argument("--root", default="~/taskops-boards")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8787)
    host = sub.add_parser("server", help="operate this HOST (over ssh, once): its owner")
    host.add_argument("action", choices=["init"])
    host.add_argument("--root", default="~/taskops-boards")
    host.add_argument("--key", default="", help="the owner's pubkey: a path, or - for stdin")
    host.add_argument("--owner", default="", help="the owner's name (default: $USER)")
    _board(sub)
    _grants(sub)
    tidy = sub.add_parser("tidy", help="remove integrated worktrees and branches")
    tidy.add_argument("--trunk", default="")
    sub.add_parser("ui", help="the dashboard: serve if needed, open the browser, token included")
    hook = sub.add_parser("hook", help="internal: what the installed hooks call")
    # `credential` is git's credential helper (`cli/gitremote.py`) — internal in
    # exactly the same sense as the other three: git invokes it, never a human.
    hook.add_argument("which", choices=["trailer", "commit", "claude", "credential"])
    hook.add_argument("rest", nargs="*")
    return parser


def _join(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    join = sub.add_parser("join", help="join a board and install the hooks")
    join.add_argument(
        "url",
        nargs="?",
        default="",
        help="<name>, <host>/<name>, or nothing (the recorded/directory name) — "
        "a full https:// URL with ?token= or ?invite= keeps working",
    )
    join.add_argument("--as", dest="actor", default="", help="dev:<name> (default: $USER)")
    join.add_argument(
        "--invite",
        default="",
        help="first join: the single-use id from `taskops invite` — your key is enrolled with it",
    )
    join.add_argument(
        "--discard-local",
        action="store_true",
        help="a local board here is archived instead of orphaned by the join",
    )
    join.add_argument(
        "--key",
        default="",
        help="overrides the discovered ssh key (its .pub is what gets registered)",
    )


def _board(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    boards = sub.add_parser("board", help="create or list the boards on a host")
    boards.add_argument(
        "action",
        choices=["create", "ls", "push", "pull", "rm", "visibility", "forge"],
    )
    boards.add_argument("target", nargs="?", default="", help="<host>/<name>, or just <name>")
    # ONE positional after the action is that action's VALUE and not the board —
    # `board visibility public`, `board forge owner/repo`. argparse fills left to
    # right and cannot know that, so `operate.py` does the swap; the choices that
    # used to live on this slot moved there with it, since the two actions do not
    # share a vocabulary and each already refuses its own typos by name.
    boards.add_argument(
        "value",
        nargs="?",
        default="",
        help="visibility: public|private (public means ANONYMOUS READ — writing always "
        "needs a key) · forge: the <owner>/<repo> whose GitHub membership opens the board",
    )
    boards.add_argument(
        "--need",
        default="",
        choices=["", *forge.NEEDS],
        help=f"forge: the access on that repo that opens the board (default: {forge.PUSH})",
    )
    boards.add_argument(
        "--clear", action="store_true", help="forge: no repo opens this board — invite-only again"
    )
    boards.add_argument("--key", default="", help="the ssh key that signs you in")
    boards.add_argument("--invite", default="", help="push: register that key first")
    # NOT `--force`, and never an alias for one (ARCHITECTURE.md §11): the flag
    # that destroys a history has to name the history.
    boards.add_argument(
        "--discard-history",
        action="store_true",
        help="board rm: destroy a history this checkout does not hold — say so out loud",
    )
    boards.add_argument("--as", dest="principal", default="", help=AS_HELP)


def _grants(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    invite = sub.add_parser("invite", help="a single-use link for a teammate")
    invite.add_argument("who", nargs="?", default="")
    invite.add_argument("--board", default="")
    invite.add_argument("--host", default="", help="the server (default: the one you joined)")
    invite.add_argument("--key", default="", help="the ssh key that signs you in")
    invite.add_argument("--as", dest="principal", default="", help=AS_HELP)
    # `--root` is BREAK-GLASS and so it has no default: passing it is the deliberate
    # choice to work on the files, on the box, when the API is what broke.
    invite.add_argument("--root", default="", help="break-glass: the boards dir, ON the host")
    kill = sub.add_parser("revoke", help="a key or an invite stops working")
    kill.add_argument("--key", default="", help="a fingerprint: SHA256:…")
    kill.add_argument("--invite", default="", help="a credential id")
    kill.add_argument("--host", default="")
    # NOT `--key`: on this verb that word is already the fingerprint being revoked.
    kill.add_argument("--sign-key", default="", help="the ssh key that signs YOU in")
    kill.add_argument("--as", dest="principal", default="", help=AS_HELP)
    kill.add_argument("--root", default="", help="break-glass: the boards dir, ON the host")
