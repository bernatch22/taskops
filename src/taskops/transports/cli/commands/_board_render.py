"""What `taskops board` prints — and the one refusal it has to phrase well.

Split from the command because that module hit its budget and because these are two different
jobs: that one decides what to ask the server, this one decides what a person reads. Every
string here ends in a command that can be pasted, which is the rule the login already keeps —
a list of names makes the reader compose the next line, and composing it by hand is the step
this whole surface exists to remove.
"""

from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Any

from ...._errors import BadRequest, TaskopsError
from ....usecases._moved import moved_note
from ....usecases.boards import name_from

__all__ = ["plan_of", "created", "listed", "viewed", "no_session"]


def plan_of(root: Path, given_server: str, given_github: str, given_name: str,
            origin: str, known: str) -> dict[str, str]:
    """What `create` is about to do, resolved from flags then from the checkout then refused."""
    server = (given_server or known).strip().rstrip("/")
    if not server:
        raise BadRequest("which server? pass `--server https://…`, or run `taskops login "
                         "<server>` once and it becomes the default")
    # NO GitHub is a board, not an error. This used to refuse here, and the refusal was the
    # first thing anybody hit: a checkout with no origin, a repository on a GitLab, a directory
    # not in git at all — all of them met "pass --github owner/repo" at the very first command,
    # for a server that never needed GitHub to hold a board. What GitHub buys is an ACCESS LIST
    # that revokes itself; without one the board's token is the door and `board invite` cuts
    # per-person codes off it. Both are real, so both are reachable from the same line.
    github = (given_github or origin).strip()
    # `.resolve()` and not `root.name`: `--repo` defaults to `.`, whose `Path` has an EMPTY
    # name, so the fallback refused with "cannot make a board name out of ``" — about a
    # directory that has a perfectly good one.
    fallback = name_from(github) if github else name_from(root.resolve().name)
    return {"server": server, "github": github, "name": given_name.strip() or fallback}


def created(plan: dict[str, str], answer: dict[str, Any], migrated: int) -> str:
    """The receipt, ending in the line the team is about to be sent.

    Two endings, because the two kinds of board are joined differently and telling somebody the
    wrong one costs them the whole flow: a linked board needs no URL and no code, and a
    tokenless one needs a per-person invite. The MIDDLE is identical, so it is written once.
    """
    url = f"{plan['server']}/{plan['name']}"
    return "\n".join([
        f"created {url}",
        *(_linked_to(plan, answer) if plan["github"] else _by_invitation()),
        f"  remote configured, {migrated} event(s) migrated",
        "",
        "  commit .taskops/board.json so your team needs no URL:",
        "    git add .taskops/board.json && git commit -m 'the board lives here'",
        "",
        *(["  then they run, in their own clone:", "    taskops join"] if plan["github"]
          else ["  then invite them, one line each:", "    taskops board invite <name>"]),
        moved_note(url),
    ])


def _linked_to(plan: dict[str, str], answer: dict[str, Any]) -> list[str]:
    return [f"  linked to {plan['github']} — push access to that repo is the invitation",
            f"  signed in as {answer.get('login', '')}"]


def _by_invitation() -> list[str]:
    """No repository, so no access list — and saying so is the point. The token is now in
    `remote.json` on this machine and nowhere else; it is never printed twice and it is not
    printed here, because a receipt is the first thing anybody pastes into a chat."""
    return ["  no GitHub behind it — the board's token is its door, and it is in .taskops/",
            "    remote.json on this machine only (gitignored, never printed twice)"]


def listed(server: str, boards: list[dict[str, str]]) -> str:
    if not boards:
        return f"no boards you can reach on {server} — `taskops board create` makes one"
    width = max(len(str(row.get("name", ""))) for row in boards)
    lines = [f"{server}"]
    lines += [f"  {str(row.get('name', '')).ljust(width)}   {server}/{row.get('name', '')}"
              for row in boards]
    return "\n".join(lines)


def viewed(url: str, *, open_browser: bool) -> str:
    if not url:
        raise BadRequest("this repository has no board — `taskops board create`, or "
                         "`taskops join <url>` if somebody else already made one")
    if open_browser:
        webbrowser.open(url + "/")
    return url


def no_session(server: str) -> TaskopsError:
    """Returned, not raised, so the caller's `raise` is where the flow stops.

    The one refusal worth phrasing: it is what somebody hits after cloning, and the difference
    between this and a bare 401 is whether they know what to type next.
    """
    if not server:
        return BadRequest("not signed in to any taskops server — `taskops login <server>`, or "
                          "pass `--server https://…`")
    return BadRequest(f"not signed in to {server} — run:\n\n    taskops login {server}")


