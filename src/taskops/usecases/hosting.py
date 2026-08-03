"""Creating a board from a laptop — the verb that removes the ssh from getting started.

Until this existed, starting a team board meant logging into the server, running `serve init`,
copying a minted token out of the output and pasting it into a chat. Every one of those steps
is a habit nobody wants: nobody `ssh`s into github.com to make a repository, and a link with a
secret in it is a secret in everybody's scrollback.

**The authorisation is the same question the login already asks, one step earlier.** Logging in
means "which linked repositories may you push to"; creating means "may you push to the one you
are naming". So the rule is: *you may create a board for a repository you can already write
to.* Nothing is granted that GitHub had not granted first, and the board is bound at birth to
something the caller demonstrably controls.

Order is load-bearing: GitHub is asked BEFORE anything is written, so a refused request leaves
no directory, no store and no minted token behind.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .._errors import BadRequest
from ..contracts.hosting import NAME
from ._ghlink import SLUG, write_link
from ._sessions import mint
from .accounts import NoAccess, authenticate, may_push, whoami
from .provision import exists, provision

__all__ = ["create_hosted", "create_open"]


def create_open(root: Path, name: str, login: str = "") -> dict[str, Any]:
    """A board with NO GitHub behind it: provision it and hand back its token.

    The other half of this module, and the one that makes the three-command start real —
    `remote add`, `board create`, `board invite` — for the projects that are the majority of
    what people actually have: a checkout with no origin, a repository on a GitLab, a directory
    that is not in git at all. Wiring the GitHub path first and calling it "the way to create a
    board" made every one of those a refusal at the first command.

    **The token IS the authorisation, and it travels back to the caller** for `remote.json` to
    hold. From there `board invite` works unchanged — the right to invite is the right to write,
    and it reads that same file.

    A SESSION comes back too, over this board alone, and it is what closes the hole the first
    version left: sessions are otherwise minted from GitHub, so a board with no repository
    behind it could never appear in anybody's `/api/projects` — you created one from your
    laptop and the server's front page did not list it. Redeeming an invite already mints
    exactly this shape; the person who MADE the board deserves it at least as much.

    `login` is a LABEL and not an identity, and this is the one place in taskops where those
    come apart. Nothing here can verify a name — there is no identity provider on this path by
    construction — but nothing rides on it either: authorisation is the token and the session's
    own project list, both minted here, and neither consults it.

    Who may CALL this is not decided here. It is a deployment question and it is the server's:
    `taskops serve --no-create` shuts the door, and a box facing strangers should use it.
    """
    wanted = name.strip()
    if not NAME.match(wanted):
        raise BadRequest(f"'{wanted}' cannot name a board — use [a-z0-9-], 1 to 40 characters, "
                         f"because the name is also a URL segment")
    if exists(root, wanted):
        raise BadRequest(f"a board called `{wanted}` is already on this server — pick another "
                         f"name, or `taskops join` it if it is the one you meant")
    token = provision(root, wanted)
    return {"name": wanted, "github": "", "token": token,
            "login": login.strip(), "session": mint(root, login.strip(), [wanted])}


def create_hosted(root: Path, github_token: str, name: str, github: str) -> dict[str, Any]:
    """Provision `<root>/<name>`, link it to `github`, and sign the caller in to it.

    Returns what `authenticate` returns plus the board — so one round trip both creates the
    board and leaves the caller holding a session for it. A second `login` would be a step that
    exists only because the code was split, which is the kind of step people blame the tool for.
    """
    token = github_token.strip()
    slug, wanted = github.strip(), name.strip()
    _shapes(wanted, slug)
    login = whoami(token)
    if not may_push(token, slug):
        raise NoAccess(f"the GitHub account {login or 'you sent'} cannot push to {slug} — a "
                       f"board is created for a repository you can already write to. Ask its "
                       f"owner for write access, or name a repository of yours.")
    if exists(root, wanted):
        raise BadRequest(f"a board called `{wanted}` is already on this server — pick another "
                         f"name, or `taskops join` it if it is the one you meant")
    provision(root, wanted)
    write_link(root / wanted, slug)
    return {**authenticate(root, token), "name": wanted, "github": slug}


def _shapes(name: str, slug: str) -> None:
    """Both shapes, checked before the network. A malformed slug is pasted into a GitHub URL
    path, so refusing it here is refusing to make the request at all — and a bad name would
    otherwise be discovered only after two calls to GitHub had already been spent."""
    if not NAME.match(name):
        raise BadRequest(f"'{name}' cannot name a board — use [a-z0-9-], 1 to 40 characters, "
                         f"because the name is also a URL segment")
    if not SLUG.match(slug):
        raise BadRequest(f"'{slug}' is not a GitHub repository — write it as owner/repo, "
                         f"exactly as it appears in the URL of the repository page")
