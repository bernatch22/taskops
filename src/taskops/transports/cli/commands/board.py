"""`taskops board` — the board as an OBJECT: make one, list them, see who can reach it.

Shaped like `gh repo`, deliberately, because it is the same job: the thing being configured
already exists on GitHub and the tool should read it rather than interview you about it. So
`board create` takes no arguments in the normal case — the repository is `origin`, the name is
the repository's, and the server is the one this machine is signed in to.

The GitHub token is FOUND by `login`'s finder, imported rather than repeated: `gh auth token`
and a hidden prompt are facts about a terminal, and there must be exactly one place that knows
which of the two to try.

There is no `board access add`. Access IS push access to the repository, so granting it is a
`gh` command — see `_board_render.access_of`, which prints the two lines that do it.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ....usecases import add_remote, push, read_remote
from ....usecases._boardfile import write_pointer
from ....usecases._routing import whoami
from ....usecases.boards import boards_of, create_board, origin_slug
from ._board_access import access_of
from ._board_invite import run_invite
from ._board_render import created, listed, plan_of, viewed
from ._board_where import server_of, signed_in
from ._shared import repo_of
from .login import github_token

__all__ = ["register", "run"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("board", help="this repo's board: create it, list yours, "
                                          "see who can reach it")
    parser.add_argument("verb", nargs="?", default="list",
                        choices=("create", "list", "view", "access", "invite"))
    parser.add_argument("who", nargs="?", default="",
                        help="with create: the board's name. With invite: the person's name, "
                             "as the board will record them")
    parser.add_argument("--withdraw", action="store_true",
                        help="with invite: take back a code that has not been used")
    parser.add_argument("--repo", default=".", help="path in the repository")
    parser.add_argument("--server", default="", help="the taskops server (default: the one "
                                                     "this machine is signed in to)")
    parser.add_argument("--name", default="", help="the board's name (default: the repo's)")
    parser.add_argument("--github", default="", help="owner/repo (default: this repo's origin)")
    parser.add_argument("--web", action="store_true", help="with view: open a browser")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    root = repo_of(args)
    if args.verb == "create":
        return _create(args, root)
    if args.verb == "invite":
        return run_invite(args, root)
    if args.verb == "view":
        return viewed(_url(root), open_browser=bool(args.web))
    # Below this line every verb asks the SERVER about you, so it needs a session. `create` and
    # `invite` are above it because they do not: one carries a GitHub token, the other the
    # board's own credential out of `remote.json`.
    server, session = signed_in(str(args.server), _url(root))
    boards = boards_of(server, session)
    if args.verb == "access":
        return access_of(_url(root), str(args.github) or _linked(root, server, boards))
    return listed(server, boards)


def _linked(root: Path, server: str, boards: list[dict[str, str]]) -> str:
    """What THIS repository's board is linked to, according to the server.

    Asked of the server and not of the local `origin`, which is what it used to read: a board is
    routinely bound to a repository that is not the checkout's remote — that is exactly how a
    project hosted somewhere other than GitHub gets a real access list — and reading the remote
    made `board access` answer "not linked to a GitHub repository" about a board that was
    linked. On a question about who can get in, that is the worst possible wrong answer.
    """
    name = _url(root).rsplit("/", 1)[-1] if _url(root).startswith(server) else ""
    return next((str(row.get("github", "")) for row in boards if row.get("name") == name), "")


def _create(args: argparse.Namespace, root: Path) -> str:
    """Read the checkout, ask the server, then wire this clone to what came back."""
    # `board create test` — the POSITIONAL names the board, because that is what everybody
    # types and `gh repo create <name>` is the shape it is copied from. `--name` still wins,
    # so the flag documented before this existed keeps meaning what it said.
    plan = plan_of(root, str(args.server), str(args.github),
                   str(args.name) or str(args.who),
                   origin_slug(root), server_of(str(args.server)))
    # The GitHub token is only FETCHED when there is a repository to check it against. Asking
    # for it unconditionally is what made a tokenless board impossible on a machine with no
    # `gh`: the finder falls through to a hidden prompt, so `board create` on a laptop without
    # GitHub sat there waiting for a secret that was about to be ignored.
    answer = create_board(plan["server"], github_token() if plan["github"] else "",
                          plan["name"], plan["github"], login=whoami(root, ""))
    minted = str(answer.get("token") or "")
    return created(plan, answer, _wire_up(root, plan["server"], plan["name"], minted))


def _wire_up(root: Path, server: str, name: str, token: str = "") -> int:
    """Point this clone at the new board and send whatever it already had.

    The migration happens HERE rather than being left to the reader: a board created from a
    project that already had local history, and then not pushed, is a board that silently
    disagrees with the repository it was made for — and the person who finds out is whoever
    joins tomorrow and sees an empty board.
    """
    url = f"{server}/{name}"
    write_pointer(root, url)
    if read_remote(root) is None:
        # The minted token, when the board has no GitHub behind it. Without passing it here
        # `add_remote` falls back to the session for that server — and a tokenless board never
        # produced one, so the remote was written with an empty credential and every write to
        # the board it had just created came back 401.
        add_remote(root, url, token)
    return int(push(root).accepted)


def _url(root: Path) -> str:
    found = read_remote(root)
    return found["url"] if found else ""
