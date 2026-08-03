"""`taskops board` from a laptop: create one, list the ones you can reach, see who else can.

The client half of `usecases.hosting`. It talks to a server over the same `Wire` the login
uses, and it does the one thing the server cannot: read the git remote of the checkout you are
standing in, so `board create` needs no arguments at all — the `gh repo create` trick, and for
the same reason. A name you have to invent for something that already has one is a name that
disagrees with it by Friday.

**Nothing here decides access.** `access` is a READ that asks GitHub, because GitHub is where
the answer lives; there is deliberately no `board access add`, since a user list here would be
a copy of the repository's collaborators and copies go stale the day somebody is removed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .._errors import BadRequest, TaskopsError
from ._sessionfile import save_session
from ._wireclient import Wire

__all__ = ["create_board", "invite_to", "withdraw_invite", "redeem_invite",
           "boards_of", "origin_slug", "name_from"]


def create_board(server: str, github_token: str, name: str, github: str,
                 login: str = "") -> dict[str, Any]:
    """Ask a server for a board and remember the session it hands back.

    The session is stored HERE rather than by the caller because a create that left the machine
    signed out would be one round trip that ends in "now run login" — the shape this command
    exists to delete.
    """
    try:
        answer = Wire(server, "").call("POST", "/api/boards",
                                       body={"github_token": github_token.strip(),
                                             "name": name, "github": github,
                                             # A LABEL for a board with no GitHub behind it —
                                             # the server cannot verify it and nothing rides on
                                             # it. Ignored entirely on the GitHub path, where
                                             # the identity comes back from `/user`.
                                             "login": login})
    except TaskopsError as refused:
        raise _older_server(server, refused) from refused
    if session := str(answer.get("session") or ""):
        save_session(server, session, str(answer.get("login") or ""))
    return answer


def _older_server(server: str, refused: TaskopsError) -> TaskopsError:
    """A server with no `/api/boards` answers about the wrong thing entirely.

    The path falls through to the per-project mount, which sees `api` as a board name it does
    not have and says **`no such project`** — a true sentence about a question nobody asked. Hit
    live against a 0.2.0 box, and the reader's only clue that the SERVER is old is a message
    that reads like a typo in their own command.

    Recognised by the server's own error code rather than by a version handshake: there is no
    version on this wire, and adding one to diagnose a 404 would be a protocol change to
    improve an error message.
    """
    if "no such project" not in str(refused).lower():
        return refused
    return TaskopsError(
        f"{server} does not know how to create a board — it is running a taskops older than "
        f"yours (`/api/boards` arrived in 0.4.0). Upgrade the server, or make the board on "
        f"the box itself: `taskops serve init <name>` then "
        f"`taskops serve link <name> --github <owner>/<repo>`.")


def invite_to(board_url: str, credential: str, who: str, by: str) -> dict[str, Any]:
    """Mint an invite on a board. `board_url` is the full `<server>/<board>`.

    Sent to the board's own mount rather than to the server root, which is what makes the
    authorisation free: whoever may already write to this board is exactly who may invite
    somebody to it, and the mount's `Policy` decides that before this route is reached.
    """
    return Wire(board_url, credential).call("POST", "/api/invite",
                                            body={"who": who, "by": by})


def withdraw_invite(board_url: str, credential: str, who: str) -> dict[str, Any]:
    return Wire(board_url, credential).call("POST", "/api/invite",
                                            body={"who": who, "withdraw": True})


def redeem_invite(server: str, board: str, code: str) -> dict[str, Any]:
    """Spend an invite and remember the session. No credential is sent — the code is one."""
    answer = Wire(server, "").call("POST", "/api/invite/redeem",
                                   body={"board": board, "code": code})
    if session := str(answer.get("session") or ""):
        save_session(f"{server}/{board}", session, str(answer.get("login") or ""))
    return answer


def boards_of(server: str, session: str) -> list[dict[str, str]]:
    """Every board that session opens, as `{name, path}`. The server builds the paths."""
    answer = Wire(server, session).call("GET", "/api/projects")
    found = answer.get("projects")
    return [row for row in found if isinstance(row, dict)] if isinstance(found, list) else []


def origin_slug(root: Path) -> str:
    """`owner/repo` from this checkout's `origin`, or "" when it cannot be read as one.

    Both URL shapes GitHub hands out, because a team uses both and neither is the wrong one:
    `git@github.com:owner/repo.git` and `https://github.com/owner/repo.git`. Anything that is
    not GitHub answers "" — the caller then asks for `--github`, which is a better sentence
    than a slug guessed out of a GitLab URL.
    """
    url = _origin(root)
    if "github.com" not in url:
        return ""
    tail = url.split("github.com", 1)[1].lstrip(":/")
    slug = tail[:-4] if tail.endswith(".git") else tail
    return slug.strip("/") if slug.count("/") == 1 else ""


def _origin(root: Path) -> str:
    try:
        done = subprocess.run(["git", "remote", "get-url", "origin"], cwd=root,
                              capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def name_from(slug: str) -> str:
    """The repository's own name, lowercased, as the board's default name.

    `owner/My-Repo` -> `my-repo`. Underscores and dots become dashes because `NAME` refuses
    them and a person who has to be told twice what characters a name may hold is a person the
    tool failed. A slug that cannot yield one raises where it can be read.
    """
    tail = slug.split("/")[-1].lower()
    cleaned = "".join(char if char.isalnum() else "-" for char in tail).strip("-")
    if not cleaned:
        raise BadRequest(f"cannot make a board name out of `{slug}` — pass one with `--name`")
    return cleaned[:40]
