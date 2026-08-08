"""Where this repo lives on the web — read from `origin`, parsed, never guessed.

The dashboard wants to link a sha to a page, and a REMOTE dashboard has no
repo to ask: the fact has to enter the board as an event, written by the side
that HAS the repo (`cli/commands.py`, at init and join). This module is that
side's reader — the parse, and nothing else.

**No origin, no answer.** `origin_url` returns "" and the caller records
nothing: a board without a remote behaves byte-for-byte like today.

**The stored shape is `{host, slug, url}`, all three.** The full https base URL
is the primitive a link is built from, but a link is not `f"{url}/commit/{sha}"`
everywhere — GitHub's is exactly that and GitLab's is `/-/commit/{sha}`. The
key that picks the template is the HOST, so it is stored beside the URL rather
than re-parsed out of it by every consumer; `slug` is what a screen prints.
That is the whole reason this is an object and not a bare `github` string like
v1's: a non-GitHub host becomes a VALUE here (`host: "gitlab.com"`), never a
second field and a second code path.
"""

from __future__ import annotations

from typing import Any, Protocol
from pathlib import Path

from . import run
from .._errors import TaskopsError

__all__ = ["origin_url", "parse", "of", "remember"]


class Caller(Protocol):
    """Whatever `board.open_board` returned — injected, never imported: `gitwork`
    does not choose local or remote, and `bind.py` takes the same shape."""

    def call(self, verb: str, args: dict[str, Any]) -> dict[str, Any]: ...

    def close(self) -> None: ...


def origin_url(repo: Path) -> str:
    """`git remote get-url origin`, or "" — no origin is a normal state."""
    result = run.git("remote", "get-url", "origin", cwd=repo)
    return result.out if result.ok else ""


def parse(url: str) -> dict[str, Any] | None:
    """ssh, scp-style and https alike → {host, slug, url}. Anything else → None.

        git@github.com:owner/repo.git
        ssh://git@github.com/owner/repo.git
        https://github.com/owner/repo
        https://user:token@gitlab.com/group/sub/repo.git
    """
    text = url.strip()
    if not text:
        return None
    if "://" in text:
        _, _, rest = text.partition("://")
    elif ":" in text and "/" not in text.partition(":")[0]:
        # scp-style: host and path are separated by a colon, not a slash.
        host_part, _, path_part = text.partition(":")
        rest = f"{host_part}/{path_part}"
    else:
        return None  # a local path or something we do not understand
    host, _, path = rest.partition("/")
    host = host.rpartition("@")[2] or host  # drop any user[:token]@
    host = host.partition(":")[0]  # a port belongs to the transport, not the page
    slug = path.strip("/").removesuffix(".git")
    if not host or "." not in host or "/" not in slug:
        return None
    return {"host": host, "slug": slug, "url": f"https://{host}/{slug}"}


def of(repo: Path) -> dict[str, Any] | None:
    """The repo's web home, or None. The whole switch for the feature."""
    return parse(origin_url(repo))


def remember(board: Caller, repo: Path) -> dict[str, Any] | None:
    """Tell the board where this repo lives — and CLOSE the board, always.

    Called by `_wire`, so by both `init` and `join`; the board it is given is
    opened for this one call and is this function's to close. Best effort, like
    every other push in this package: a server that does not answer must not
    make `taskops join` fail — the hooks are installed, the credential is
    written, and the next run of either command records the fact.
    """
    found = of(repo)
    try:
        if found is None:
            return None  # no origin: no event, no noise (the chapter's third rule)
        board.call("project", {"op": "remote", **found})
    except TaskopsError:
        return None
    finally:
        board.close()  # every path, including the one that recorded nothing
    return found
