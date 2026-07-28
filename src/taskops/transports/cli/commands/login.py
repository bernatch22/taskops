"""`taskops login <url>` — sign in with GitHub, and be told exactly what to type next.

This command is where the GitHub token is HANDLED, and that is why finding it lives here
rather than in the use case: `gh auth token` and a hidden prompt are both facts about a
terminal, and a use case that shelled out to `gh` could not be called from anything else.

`gh` first, because the person who has it has already solved authentication and should not be
asked again; the fallback is `getpass`, which does not echo. A token typed into a visible
prompt lands in the terminal's scrollback and, on many setups, in a shell history file — this
is the one input in taskops where that difference matters.

The output is the next command, per project, ready to paste. A list of project names would
make the reader compose that line themselves, and the whole reason this command exists is
that the previous version of this flow asked people to compose things by hand.
"""

from __future__ import annotations

import argparse
import getpass
import subprocess

from ....usecases import login as sign_in
from ....usecases import logout as sign_out
from ....usecases import session_of

__all__ = ["register"]

PROMPT = "paste a GitHub token with the `repo` scope (input hidden): "


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("login", help="sign in to a taskops server with your GitHub account")
    parser.add_argument("url", help="the server's base URL, e.g. https://taskops.example.com")
    parser.add_argument("--logout", action="store_true",
                        help="forget this machine's session for that server")
    parser.add_argument("--show", action="store_true",
                        help="print the stored session token itself (for the UI's unlock "
                             "screen) instead of signing in")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    url = str(args.url)
    if args.logout:
        return f"signed out of {sign_out(url)} — the session file no longer mentions it"
    if args.show:
        held = session_of(url)
        return f"{held['url']} as {held['login']}\n  session {held['session']}"
    done = sign_in(url, github_token())
    return _welcome(done["url"], str(done["login"]), list(done["projects"]))


def github_token() -> str:
    """`gh auth token`, else a hidden prompt. Returned, never stored, never printed."""
    return _from_gh() or getpass.getpass(PROMPT)


def _from_gh() -> str:
    """Degrades silently on purpose: no `gh`, `gh` not logged in, or `gh` hanging are all the
    same situation for the reader — nobody handed us a token — and the prompt is right there.
    The timeout is what keeps a wedged `gh` from becoming a wedged `taskops`."""
    try:
        done = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True,
                              timeout=5.0, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def _welcome(url: str, who: str, projects: list[str]) -> str:
    """The login and the projects. Never the session — a terminal is a thing people screenshot
    and share, and `--show` exists for the one time it must be visible."""
    lines = [f"signed in to {url} as {who}"]
    if not projects:
        lines.append("  no projects — that server has none you can reach yet")
        return "\n".join(lines)
    width = max(len(name) for name in projects)
    lines.append(f"  {len(projects)} project(s) — run one of these in the matching checkout:")
    lines += [f"    {name.ljust(width)}   taskops remote add {url}/{name}" for name in projects]
    return "\n".join(lines)
