"""The inhabited directories of a checkout — the main worktree and every tree
under `.taskops/trees` — named, found, and walled.

`trees.py` is the GEOMETRY (where a card's directory goes, how it is cut);
this is the READ of that geometry for a screen: which directories exist right
now, and whether a path a browser sent stays inside one of them. The Editor
(ARCHITECTURE.md §22) shows the real files of a real worktree, so the walls
here are the whole of its security posture, in three sentences:

* A tree is addressed by its DIRECTORY NAME under `.taskops/trees/` — `tk-…`,
  `_ms-…` — or by `main`, the checkout itself. `NAME` admits no slash and no
  `..`, so a name never becomes a path before `locate()` has joined it to the
  one directory it may name.
* A file is addressed by a plain repo-relative path, and `inside()` decides by
  RESOLVING both ends: the real path of the file must sit under the real path
  of the tree. A `..`, an absolute path, a doubled slash, a NUL, or a symlink
  that leaves the tree all collapse to the same answer, `None` — a path is
  refused, never repaired.
* `.git` is never a file of the project. In a linked worktree it is a FILE
  pointing at the common dir, and the common dir holds every branch's objects
  and the hooks; in the checkout it is the directory itself. Neither is code.
"""

from __future__ import annotations

import re
from typing import NamedTuple
from pathlib import Path

from . import run
from .trees import trees_dir

MAIN = "main"
"""The checkout itself, listed first: the one directory that is not a card."""

NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,80}$")
"""A tree's name — one directory name, never a path. `..` cannot match it."""


class Tree(NamedTuple):
    name: str
    path: Path
    dir: str  # repo-relative: "" for the checkout, `.taskops/trees/<name>` otherwise
    branch: str  # "" on a detached HEAD
    head: str  # the commit checked out, 40-hex, "" when git could not say


def listed(repo: Path) -> list[Tree]:
    """Every inhabited directory, the checkout first and the trees in name order.

    A directory under `trees/` with no `.git` in it is not a worktree — a stray
    folder, a removed tree git has not pruned — and is left out rather than
    shown as one: a tree on this screen is a place a worker can be."""
    found = [describe(MAIN, repo, "")]
    root = trees_dir(repo)
    if root.is_dir():
        for path in sorted(root.iterdir()):
            if path.is_dir() and (path / ".git").exists():
                found.append(describe(path.name, path, str(path.relative_to(repo))))
    return found


def locate(repo: Path, name: str) -> Path | None:
    """The directory `name` addresses, or None — the ONLY door from a string to
    a tree. The name is matched BEFORE it is joined to anything."""
    if name == MAIN:
        return repo
    if not NAME.match(name):
        return None
    path = trees_dir(repo) / name
    return path if path.is_dir() and (path / ".git").exists() else None


def inside(tree: Path, rel: str) -> Path | None:
    """The real file `rel` names inside `tree`, or None.

    Resolved on both ends, so a symlink that points outside the tree is caught
    by the same comparison that catches `..` — there is one wall, not a list of
    shapes to recognise. A path that resolves to the tree itself is refused
    too: the door reads FILES."""
    if not rel or rel.startswith(("/", "\\")) or "\\" in rel or any(ord(c) < 32 for c in rel):
        return None
    parts = rel.split("/")
    if any(part in ("", ".", "..", ".git") for part in parts):
        return None
    base = tree.resolve()
    try:
        target = (tree / rel).resolve(strict=True)
    except OSError:
        return None
    if base not in target.parents:
        return None
    return target if target.is_file() else None


def describe(name: str, path: Path, rel: str) -> Tree:
    """One inhabited directory, as the screen names it: two git questions."""
    head = run.git("rev-parse", "--verify", "--quiet", "HEAD", cwd=path)
    return Tree(
        name=name,
        path=path,
        dir=rel,
        branch=run.branch_at(path),
        head=head.out.strip() if head.ok else "",
    )
