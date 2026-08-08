"""GET /<board>/git/… — the read-only door onto the repo this host sits in.

    GET /<board>/git/commit/<ref>            the commit against its first parent
    GET /<board>/git/compare/<a>...<b>       merge-base(a, b) → b
    optional ?path=<file>   one file's patch instead of the whole range

Same envelope as `rpc.py` (always an object; a failure is
`{"ok": false, "error": {code, message}}`) and the same token door as `/rpc` —
there is no second credential system, and `server.py` checks the credential
before this module is reached.

**Whether the door exists at all is decided ONCE, at construction**, never
re-derived per request: `Mounts` carries `repo: Path | None`. `taskops ui` sits
inside a repo (its root is `<repo>/.taskops`) and passes it; `taskops serve`
sits in a boards directory and passes nothing, so every /git request there is a
404 whose message SAYS which case it is — the UI reads those words and falls
through its cascade (numstat → /git → the forge link → an honest sentence)
rather than showing a dead pane. ARCHITECTURE.md §16.

This module only routes and refuses. Everything about git is `gitwork/diff.py`,
which is where the ref validation lives.
"""

from __future__ import annotations

from typing import Any
from pathlib import Path
from urllib.parse import unquote

from .._errors import NotFound, BadRequest
from ..gitwork import diff

NO_REPO = (
    "this host serves boards, not a repository — it was started outside a "
    "checkout (taskops serve), so there is no clone here to read a diff from. "
    "A host that sits in a repo (taskops ui) answers /git."
)

SEPARATOR = "..."


def answer(repo: Path | None, tail: str, query: str) -> dict[str, Any]:
    """The whole door. `tail` is the path after `<board>/git/`."""
    if repo is None:
        raise NotFound(NO_REPO)
    kind, _, rest = tail.partition("/")
    path = _param(query, "path") or None
    if kind == "commit" and rest:
        found = diff.commit_range(repo, unquote(rest))
        if found is None:
            raise NotFound(f"this repo has no commit {unquote(rest)!r}")
    elif kind == "compare" and SEPARATOR in rest:
        left, _, right = unquote(rest).partition(SEPARATOR)
        found = diff.compare_range(repo, left, right)
        if found is None:
            raise NotFound(f"this repo does not have both {left!r} and {right!r}")
    else:
        raise BadRequest("git/commit/<ref> or git/compare/<a>...<b>")
    return diff.between(repo, found[0], found[1], path)


def _param(query: str, key: str) -> str:
    for part in query.split("&"):
        name, _, value = part.partition("=")
        if name == key:
            return unquote(value.replace("+", " "))
    return ""
