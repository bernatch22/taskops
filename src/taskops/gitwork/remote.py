"""`origin` — everything taskops knows or does about a remote, in one module.

Two halves, one switch. The READING half (`origin_url`, `parse`, `of`,
`remember`) answers where this repo lives on the web, so the board can link a
sha to a page — written by the side that HAS the repo (`cli/commands.py`, at
init and join), because a REMOTE dashboard has no repo to ask. The PUSHING half
(`has_origin`, `push`) makes branches visible there at the lifecycle moments
that already exist — best effort by construction: never a gate, never in a
commit hook, never a board fact.

**No origin, no feature, no noise.** `git remote get-url origin` is the ONE
question, asked in one place (`origin_url`); without an answer nothing is
attempted, nothing is parsed, nothing is logged — a board with no remote
behaves byte-for-byte like a taskops that never had this module.

**The stored shape is `{host, slug, url}`, all three.** The https base URL is
the primitive a link is built from, but a link is not `f"{url}/commit/{sha}"`
everywhere — GitHub's is exactly that and GitLab's is `/-/commit/{sha}`. The
key that picks the template is the HOST, so it is stored beside the URL rather
than re-parsed out of it by every consumer; `slug` is what a screen prints.
A non-GitHub host becomes a VALUE here, never a second code path.

This file was born twice in one wave — two workers, each over the 200-line
budget in a different module, each split the origin concern out under the
obvious name, neither could see the other. The same-path collision made the
merge refuse loudly (unlike the silent `ago()` twins docs/fan-out.md records),
and the halves were complementary, so the union IS the module. The lesson is
the fan-out rule, third notch: a CONCEPT named by two specs is a seam, and a
seam lands serialized first.
"""

from __future__ import annotations

from typing import Any, Protocol
from pathlib import Path

from . import run
from .._errors import TaskopsError

__all__ = ["origin_url", "parse", "of", "remember", "has_origin", "push"]

# A push is never a gate, so it may never cost more than a moment. 10s is long
# enough for a real push over a slow link and short enough that `done` stays a
# local operation in feel: worst case the worker waits ten seconds ONCE and the
# branch is pushed by the next lifecycle moment anyway.
PUSH_TIMEOUT = 10.0


class Caller(Protocol):
    """Whatever `board.open_board` returned — injected, never imported: `gitwork`
    does not choose local or remote, and `bind.py` takes the same shape."""

    def call(self, verb: str, args: dict[str, Any]) -> dict[str, Any]: ...

    def close(self) -> None: ...


# ── reading: where this repo lives on the web ────────────────────────────────


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


# ── pushing: making local history visible there ──────────────────────────────


def has_origin(path: Path) -> bool:
    """The one switch for everything that talks to a remote — the same single
    question `origin_url` asks, so the two halves cannot disagree about it."""
    return origin_url(path) != ""


def push(repo: Path, *branches: str, cwd: Path | None = None) -> None:
    """Best effort; whatever happened locally still happened.

    Every failure mode is swallowed on purpose — no origin, no network, a
    protected branch, a remote that hangs, git missing entirely. The caller has
    already done the thing that mattered; this only makes it visible on GitHub.
    Nothing is logged and nothing is recorded on the board: a push is not a
    board fact, and half-recorded infrastructure state is drift.
    """
    where = cwd or repo
    names = [name for name in branches if name]
    if not names or not has_origin(where):
        return
    for name in names:
        try:
            run.git("push", "origin", name, cwd=where, timeout=PUSH_TIMEOUT)
        except TaskopsError:  # timeout, or no git at all — never the caller's problem
            return
