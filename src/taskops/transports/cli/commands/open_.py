"""`taskops open` — the board, in a browser, without assembling a URL by hand.

Everything the board offers already existed and was reachable by nobody: the host lives in
`.taskops/remote.json`, the credential lives in the home directory, and joining the two is a
step people did in their head and got wrong. The command that fixes that is one word.

Standing in a project opens THAT project; `--projects` opens the server's own page, which lists
every board the session can reach. The default is the specific one because a person who ran this
from inside a checkout has already said which board they meant.

`webbrowser` and not `open`: the same command has to work on the Linux boxes this is deployed
to, and the stdlib already knows the answer per platform. `--print` is the escape hatch for a
terminal with no browser at all — over SSH, the URL is the useful output.

**The URL is not printed when the browser took it.** It carries a credential, and a terminal is
a thing people screenshot, paste into issues and share on a call; the browser is already holding
the secret, so echoing it only adds a copy nobody needed. It appears when it is the only way
forward — `--print`, or no browser to hand it to.
"""

from __future__ import annotations

import argparse
import webbrowser

from ....usecases import board_url, read_remote, root_url
from ....usecases.localui import local_ui
from ._shared import repo_of

__all__ = ["register"]


def register(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = sub.add_parser("open", help="open this project's board — or your projects — "
                                         "in a browser")
    parser.add_argument("--repo", default=".", help="the project to open (default: here)")
    parser.add_argument("--projects", action="store_true",
                        help="open the server's root instead: every board you can reach")
    parser.add_argument("--server", default="",
                        help="which server, when this machine is signed in to more than one")
    parser.add_argument("--print", dest="print_only", action="store_true",
                        help="print the URL instead of opening it")
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> str:
    url, note = _target(args)
    if args.print_only:
        return url
    # The URL is NOT echoed on success. It carries the credential, and a terminal is a thing
    # people screenshot, paste into issues and share on a call — printing it would put the
    # secret somewhere the browser was about to hold for us anyway. `--print` is the one place
    # it appears, because there the caller asked for it.
    if webbrowser.open(url):
        return note
    # No browser at all — over SSH, say. Here the URL is the only useful output there is, and
    # a command that refused to show it would leave the caller with nowhere to go.
    return f"no browser here — open this yourself:\n  {url}"


def _target(args: argparse.Namespace) -> tuple[str, str]:
    if args.projects or args.server:
        url, found = root_url(str(args.server))
        return url, f"your projects on {found['url']} — signed in as {found['login']}"
    root = repo_of(args)
    # LOCAL projects get a board too, and this is where that stopped being true. A project with
    # no remote used to be answered with a refusal naming `taskops ui` — a command that BLOCKS,
    # in a terminal the caller was using for something else. So `open` starts one instead: the
    # question "show me the board" has the same answer either way, and which kind of project
    # this is has never been the caller's problem.
    if read_remote(root) is None:
        if url := local_ui(root):
            return url, f"opening this project's board — a local ui is up at {url}"
        raise _no_ui()
    return board_url(str(args.repo)), "opening this project's board"


def _no_ui() -> Exception:
    """The one failure worth phrasing: we tried to start a board and it did not come up. The
    caller gets the blocking command, which is where they will see the actual error."""
    from ...._errors import TaskopsError

    return TaskopsError("could not start a local board — run `taskops ui` here to see why")
