"""GET /<board>/git/… — the read-only door onto the repo this host sits in.

    GET /<board>/git/commit/<ref>            the commit against its first parent
    GET /<board>/git/compare/<a>...<b>       merge-base(a, b) → b
    optional ?path=<file>   one file's patch instead of the whole range
    GET /<board>/git/file/<rev>?path=<file>  one committed file's BYTES at a rev

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

**`file` is not a file server, and that refusal IS the feature.** A report is a
committed file the board points at (`core/reports.py`), so the UI needs the
bytes at a sha from the reader's OWN clone — the same reason the diff doors
exist, since `events.jsonl` carries the pointer and never the content. A door
that served "any repo-relative path" would hand out the whole checkout — `.env`,
a key, the board's own sqlite — to anyone holding a read token. So the path goes
through `core/reports.py::under()`, the ONE shape rule, the same call the verb
that REGISTERS a report makes: one guard at both ends cannot drift, and it
refuses rather than repairs (a traversal normalised into something acceptable is
the bug, not the fix).
"""

from __future__ import annotations

from typing import Any
from pathlib import Path
from urllib.parse import unquote

from ..core import reports
from .._errors import NotFound, BadRequest
from ..gitwork import diff, patch

NO_REPO = (
    "this host serves boards, not a repository — it was started outside a "
    "checkout (taskops serve), so there is no clone here to read a diff from. "
    "A host that sits in a repo (taskops ui) answers /git."
)

SEPARATOR = "..."

STALE = (
    "{refs} not in your clone yet — `{fetch}` brings {them}. The board is shared and "
    "the code is not: a card's branch reaches origin when it closes, and this "
    "window reads only the checkout it stands in. Nothing is fetched for you."
)
"""The MISSING-REF case, in its own words. It is not an error and must not read
like one: on a shared board most refs belong to somebody else's card, and until
you fetch, "not here yet" is simply the truth about your disk. Naming the exact
command is this codebase's habit — every refusal names the call that works —
and it is also the reason nothing fetches on the reader's behalf: a background
`git fetch` inside a read-only door would move a branch under a worktree
somebody is sitting in."""

SHA = "0123456789abcdef"

NOT_A_REPORT = (
    "{path} is not a report. This door serves committed files under "
    f"{reports.DIR} and nothing else — it is not a file server, and a read "
    "token is not a licence to read the clone. Ask for the path a report event "
    "carries, exactly as it carries it."
)
"""The security boundary, in the words the caller gets. It names the ONE
directory rather than describing what was wrong with the path: which of `..`, a
leading `/`, a doubled slash or a plain typo it was is the caller's business,
and spelling that out only teaches a prober which wall it hit."""

ODD_SHAPE = (
    "{path} is under {dir} but is not a shape this door shows git: a report path "
    "is plain — letters, digits, `-`, `_`, `.` and `/`, up to 200 characters. "
    "Rename the file and register it again."
)
"""The SECOND wall, in its own words because it is a different fact: `under()`
says "not a report", this says "a report nobody can address". It is
`diff.usable` — one shape rule for everything this package hands git."""

ABSENT = (
    "{path} is not in {sha} — a report is served at the commit its event names, "
    "and this one does not carry that file. If it was added later, that later "
    "commit is the one to ask for."
)

HTML = "text/html"
TEXT = "text/plain"


def answer(repo: Path | None, tail: str, query: str) -> dict[str, Any]:
    """The whole door. `tail` is the path after `<board>/git/`."""
    if repo is None:
        raise NotFound(NO_REPO)
    kind, _, rest = tail.partition("/")
    path = _param(query, "path") or None
    if kind == "file" and rest:
        return _file(repo, unquote(rest), path or "")
    if kind == "commit" and rest:
        ref = unquote(rest)
        found = diff.commit_range(repo, ref)
        if found is None:
            raise NotFound(_stale(ref))
    elif kind == "compare" and SEPARATOR in rest:
        left, _, right = unquote(rest).partition(SEPARATOR)
        found = diff.compare_range(repo, left, right)
        if found is None:
            raise NotFound(_stale(*(r for r in (left, right) if not diff.resolve(repo, r))))
    else:
        raise BadRequest(
            "git/commit/<ref>, git/compare/<a>...<b>, or git/file/<rev>?path=<file>"
        )
    return patch.between(repo, found[0], found[1], path)


def _file(repo: Path, rev: str, wanted: str) -> dict[str, Any]:
    """One committed file at a rev — read-only, shape-guarded, capped.

    Three walls, in this order: the path is a REPORT path (`under()`, which
    normalises or refuses and never repairs), it is a shape git may be shown
    (`diff.usable`, the wall every ref already passes), and only then does the
    rev become a sha (`diff.resolve`, the package's one string→sha door). From
    there `patch.show` sees a 40-hex sha and a path this module vouched for, so
    nothing the browser sent reaches git as itself.

    `truncated` + `cap` is `patch.between`'s vocabulary on purpose: the UI
    reading a report is the UI reading a patch, and a second vocabulary would be
    a second renderer. `content_type` is a FIELD, never this response's header —
    every door answers `application/json`, so no path can make THIS origin, the
    one the token lives in, serve HTML; the reader sandboxes it. `text/html`
    only for a literal `.html`, because a type this door does not know must
    degrade to something no renderer will execute."""
    path = reports.under(wanted)
    if not path:
        raise BadRequest(NOT_A_REPORT.format(path=wanted or "a missing ?path="))
    if not diff.usable(path):
        raise BadRequest(ODD_SHAPE.format(path=path, dir=reports.DIR))
    sha = diff.resolve(repo, rev)
    if sha is None:
        raise NotFound(_stale(rev))
    got = patch.show(repo, sha, path)
    if got is None:
        raise NotFound(ABSENT.format(path=path, sha=sha[:12]))
    text, cut = got
    return {
        "path": path,
        "rev": sha,
        "content_type": HTML if path.endswith(".html") else TEXT,
        "text": text,
        "truncated": cut,
        "cap": patch.CAP,
    }


def _stale(*refs: str) -> str:
    """Which refs are missing, and the one command that brings them.

    A sha is asked for WITHOUT a refspec — `git fetch origin <40 hex>` is
    refused by most servers unless they allow it — while a branch is named, so
    the reader can paste the line and get exactly what the pane wanted."""
    names = [ref for ref in refs if ref] or ["that ref"]
    branches = [ref for ref in names if not _looks_like_a_sha(ref)]
    many = len(names) > 1
    return STALE.format(
        refs=f"{' and '.join(names)} {'are' if many else 'is'}",
        fetch=" ".join(["git fetch origin", *branches]),
        them="them" if many else "it",
    )


def _looks_like_a_sha(ref: str) -> bool:
    return len(ref) >= 7 and all(char in SHA for char in ref.lower())


def _param(query: str, key: str) -> str:
    for part in query.split("&"):
        name, _, value = part.partition("=")
        if name == key:
            return unquote(value.replace("+", " "))
    return ""
