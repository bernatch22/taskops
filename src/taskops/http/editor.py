"""GET /<board>/editor/… — the Editor's doors onto the worktrees of THIS checkout.

    GET /<board>/editor/trees                        every inhabited directory, the checkout first
    GET /<board>/editor/tree?tree=<name>             one tree's files: path, size, mtime, git state
    GET /<board>/editor/file?tree=&path=[&base=]     one file: its text (or "binary"), and the
                                                     lines that moved since the base, as marks
    GET /<board>/editor/diff?tree=&path=[&base=]     the same file as a unified patch
    GET /<board>/editor/feed?tree=<name>             a signal per change on disk (WebSocket, SSE)

Same envelope as `rpc.py`, same token door as `/rpc` and `/git` — the handler
checks the credential before anything here reads a byte, and a PUBLIC board's
anonymous READ opens these exactly as it opens `/git` (`auth.py::anonymous`).

**Only a WINDOW answers.** The Editor shows the real files of real worktrees,
and those live on the disk `taskops ui` runs on: `Mounts.repo` is the checkout
and the trees are under its `.taskops/trees/`. A serve-mode host (the deployed
instance) has boards and, at most, a board's bare `repo.git` — a bare repo has
no working copy and no worktrees, so there is nothing an editor could honestly
show, and `NO_CHECKOUT` says so instead of drawing an empty tree.

**Every wall is `gitwork/inhabited.py`'s.** A tree is a directory NAME matched
before it is joined to anything; a file is a repo-relative path resolved on
both ends and refused — never repaired — when it leaves the tree, names `.git`,
or is a symlink out. This module routes, reads the query, and words the
refusals; it decides nothing about paths itself.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast
from pathlib import Path

from . import rpc, feed
from .. import _clock
from .routes import param
from .._errors import NotFound, BadRequest, TaskopsError
from ..gitwork import diff, scan, reading, inhabited

if TYPE_CHECKING:
    from .server import BoardServer
    from .handler import Handler
    from .treewatch import Held, Trees

NO_CHECKOUT = (
    "this host serves boards, not a checkout — the Editor reads the worktrees on "
    "the disk `taskops ui` runs on, and this process was started outside one "
    "(taskops serve). Run `taskops ui` in a checkout joined to this board and the "
    "page reads your own trees."
)

NO_TREE = (
    "no worktree named {name!r} here — `editor/trees` lists the ones that exist: "
    "`main` for the checkout, and every directory under .taskops/trees/"
)

OUTSIDE = (
    "{path} is not a file inside that worktree. This door reads the files of ONE "
    "inhabited directory and nothing else — no `..`, no absolute path, no symlink "
    "that leaves it, and never `.git`."
)
"""The security boundary, in the words the caller gets. One sentence for every
shape of escape, on `gitdoor.NOT_A_REPORT`'s reasoning: naming which wall was
hit only teaches a prober where the next one is."""

ODD_BASE = (
    "{ref} is not a shape this door shows git as a base: a branch name or a sha, "
    "plain — letters, digits, `/`, `-`, `_`, `.`, up to 200 characters."
)

ROUTES = "editor/trees, editor/tree?tree=, editor/file?tree=&path=, editor/diff?tree=&path=, editor/feed?tree="


def serve(handler: Handler, board: str, rest: str) -> None:
    """The whole door, from the router: `rest` is the path after `editor/`."""
    query = handler.path.partition("?")[2]
    trees = cast("BoardServer", handler.server).editor
    if rest == "feed":
        _stream(handler, trees, board, query)
        return

    def run(_: dict[str, Any]) -> dict[str, Any]:
        handler.mounts.check(board)
        handler._credential(board, "read")  # noqa: SLF001
        return answer(handler.mounts.repo, trees, board, rest, query)

    handler._answer(run)  # noqa: SLF001


def answer(repo: Path | None, trees: Trees, board: str, rest: str, query: str) -> dict[str, Any]:
    if repo is None:
        raise NotFound(NO_CHECKOUT)
    if rest == "trees":
        return {
            "checkout": str(repo),
            "trees": [
                {"name": t.name, "dir": t.dir, "branch": t.branch, "head": t.head}
                for t in inhabited.listed(repo)
            ],
        }
    if rest not in ("tree", "file", "diff"):
        raise BadRequest(ROUTES)
    name, tree = _named(repo, param(query, "tree"))
    if rest == "tree":
        return _listing(name, tree, trees.listing(trees.key(board, name), tree))
    rel, path = _file_in(tree, param(query, "path"))
    base = _base(tree, param(query, "base"))
    is_tracked = reading.tracked(tree, rel)
    if rest == "diff":
        text, cut = ("", False) if base is None else reading.patch_of(
            tree, base.sha, rel, is_tracked=is_tracked
        )
        return _named_file(name, rel, base) | {"patch": text, "truncated": cut, "cap": reading.CAP}
    got = reading.read(path)
    lines = got.text.count("\n") + (1 if got.text and not got.text.endswith("\n") else 0)
    marks: list[reading.Mark] = []
    if base is not None and not got.binary:
        marks = reading.marks(tree, base.sha, rel, is_tracked=is_tracked, lines=lines)
    return _named_file(name, rel, base) | {
        "text": got.text,
        "binary": got.binary,
        "size": got.size,
        "mtime": got.mtime,
        "truncated": got.truncated,
        "cap": reading.CAP,
        "tracked": is_tracked,
        "marks": [[m.start, m.end, m.kind] for m in marks],
    }


def _stream(handler: Handler, trees: Trees, board: str, query: str) -> None:
    """The feed for one tree: the same `feed.attach` the board's feed uses, on a
    key of its own, and the watcher started on the way in (`treewatch.py`)."""
    try:
        handler.mounts.check(board)
        handler._credential(board, "read")  # noqa: SLF001
        if handler.mounts.repo is None:
            raise NotFound(NO_CHECKOUT)
        name, tree = _named(handler.mounts.repo, param(query, "tree"))
    except TaskopsError as err:
        handler._fail(rpc.status_for(rpc.failure(err)), err)  # noqa: SLF001
        return
    key = trees.key(board, name)
    trees.watch(key, tree, name)
    wanted = handler.headers.get("Upgrade", ""), handler.headers.get("Sec-WebSocket-Key", "")
    feed.attach(handler, handler.mounts.hub, key, *wanted)


def _named(repo: Path, name: str) -> tuple[str, Path]:
    tree = inhabited.locate(repo, name) if name else None
    if tree is None:
        raise NotFound(NO_TREE.format(name=name or "?tree="))
    return name, tree


def _file_in(tree: Path, rel: str) -> tuple[str, Path]:
    path = inhabited.inside(tree, rel)
    if path is None:
        raise BadRequest(OUTSIDE.format(path=rel or "a missing ?path="))
    return rel, path


def _base(tree: Path, ref: str) -> reading.Base | None:
    """The base asked for, resolved — or None, which the answer carries as
    `base: null` and the page draws as "no base to compare against". A ref that
    could be read as an option never reaches git (`diff.usable`, the wall every
    ref of the /git door passes); the path needs no such wall — it goes after
    `--`, where git reads nothing as an option."""
    if ref and not diff.usable(ref):
        raise BadRequest(ODD_BASE.format(ref=ref))
    return reading.base_of(tree, ref)


def _listing(name: str, tree: Path, held: Held) -> dict[str, Any]:
    described = inhabited.describe(name, tree, "")
    return {
        "tree": name,
        "branch": described.branch,
        "head": described.head,
        "files": [
            {"path": e.path, "size": e.size, "mtime": e.mtime, "state": e.state}
            for e in held.scan.files.values()
        ],
        "capped": held.scan.capped,
        "total": held.scan.total,
        "cap": scan.FILE_CAP,
        "seq": held.seq,
        "at": _clock.now(),
    }


def _named_file(name: str, rel: str, base: reading.Base | None) -> dict[str, Any]:
    return {
        "tree": name,
        "path": rel,
        "base": {"ref": base.ref, "sha": base.sha} if base is not None else None,
    }
