"""GET /<board>/git/… — the read-only door onto the repo this host sits in.

    GET /<board>/git/commit/<ref>            the commit against its first parent
    GET /<board>/git/compare/<a>...<b>       merge-base(a, b) → b
    optional ?path=<file>   one file's patch instead of the whole range
    GET /<board>/git/file/<rev>?path=<file>  one committed file's BYTES at a rev

Same envelope as `rpc.py` (always an object; a failure is
`{"ok": false, "error": {code, message}}`) and the same token door as `/rpc` —
there is no second credential system, and `server.py` checks the credential
before this module is reached.

**WHICH repo answers is `http/repos.py`'s decision, per board.** `taskops ui`
sits inside a repo (its root is `<repo>/.taskops`) and passes its checkout for
every board; `taskops serve` sits in a boards directory and answers from the
board's OWN `<root>/<board>/repo.git` (§16, "The host becomes the remote" — the
pull mirror that stood here for one day is retired). So `NO_REPO` means "no
checkout here, and nobody has pushed this board's code to this host yet", never
"this host can never read git" — the UI falls through its cascade rather than a
dead pane.

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

from . import stale
from ..core import reports
from .._errors import NotFound, BadRequest
from ..gitwork import diff, patch

NO_REPO = (
    "this host serves boards, not a repository — it was started outside a "
    "checkout (taskops serve), and nothing has been pushed to this board's git "
    "here yet, so there is no history to read a diff from. Two ways in: push "
    "to this board's remote (`taskops remote` names it, and a worktree joined "
    "to the board pushes every commit on its own), or run `taskops ui` in a "
    "checkout, where the window reads your own clone."
)
"""The serve-mode refusal, naming the moves that open it. It is a BOARD-level
fact with a board-level remedy — the mirror's `NO_FORGE` retired into it
(`http/repos.py`), because the forge is no longer a source and its absence is
therefore no longer a reason a diff cannot be read."""

SEPARATOR = "..."

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
MARKDOWN = "text/markdown"


def answer(
    repo: Path | None, tail: str, query: str, *, hosted: bool = False
) -> dict[str, Any]:
    """The whole door. `tail` is the path after `<board>/git/`. `hosted` is
    True when the repo is the board's own, on a serve-mode host, and False for
    a window's clone (`http/repos.py`): the one fact still travelling, and it
    decides only the AUDIENCE of a missing-ref refusal (`http/stale.py`). The
    bounded on-demand fetch it used to license retired with the pull mirror —
    the board's own repository IS the source, so there is nowhere to fetch
    from and a missing ref is answered at once."""
    if repo is None:
        raise NotFound(NO_REPO)
    kind, _, rest = tail.partition("/")
    path = _param(query, "path") or None
    if kind == "file" and rest:
        return _file(repo, unquote(rest), path or "", hosted)
    if kind == "commit" and rest:
        ref = unquote(rest)
        found = diff.commit_range(repo, ref)
        if found is None:
            raise NotFound(stale.sentence(ref, hosted=hosted))
    elif kind == "compare" and SEPARATOR in rest:
        left, _, right = unquote(rest).partition(SEPARATOR)
        found = diff.compare_range(repo, left, right)
        if found is None:
            missing = [r for r in (left, right) if not diff.resolve(repo, r)]
            raise NotFound(stale.sentence(*missing, hosted=hosted))
    else:
        raise BadRequest(
            "git/commit/<ref>, git/compare/<a>...<b>, or git/file/<rev>?path=<file>"
        )
    return patch.between(repo, found[0], found[1], path)


def _file(repo: Path, rev: str, wanted: str, hosted: bool) -> dict[str, Any]:
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
    one the token lives in, serve HTML; the reader sandboxes it. The three types
    `_kind` answers are argued there."""
    path = reports.under(wanted)
    if not path:
        raise BadRequest(NOT_A_REPORT.format(path=wanted or "a missing ?path="))
    if not diff.usable(path):
        raise BadRequest(ODD_SHAPE.format(path=path, dir=reports.DIR))
    sha = diff.resolve(repo, rev)
    if sha is None:
        raise NotFound(stale.sentence(rev, hosted=hosted))
    got = patch.show(repo, sha, path)
    if got is None:
        raise NotFound(ABSENT.format(path=path, sha=sha[:12]))
    text, cut = got
    return {
        "path": path,
        "rev": sha,
        "content_type": _kind(path),
        "text": text,
        "truncated": cut,
        "cap": patch.CAP,
    }


def _param(query: str, key: str) -> str:
    for part in query.split("&"):
        name, _, value = part.partition("=")
        if name == key:
            return unquote(value.replace("+", " "))
    return ""


def _kind(path: str) -> str:
    """The three answers, and the default keeps itself safe: an unrecognised
    type falls to `text/plain`, which every reader draws as characters. Decided
    HERE and never in the browser — `ReportFrame` reads what the door SAYS a
    file is, never the extension it can see, so the two cannot drift apart."""
    if path.endswith(".html"):
        return HTML
    return MARKDOWN if path.endswith(".md") else TEXT
