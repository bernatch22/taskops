"""One worktree, listed and measured: what git says is in the project, what the
disk says about each file, and whether two such readings differ.

The LISTING is git's, because "in the project" is git's fact: the index names
the tracked files and the untracked walk honours every `.gitignore` on the way,
so `node_modules`, a `.venv` and a build output are left out by the same rule
the worker's own `git status` uses. The MEASURE is the stdlib's — one `stat`
per file, mtime and size — because that is the honest way to notice a file
changed without a watcher dependency this package refuses to carry
(ARCHITECTURE.md §11), and it is cheap: a few thousand `stat`s is a
millisecond or two, and the watcher (`http/treewatch.py`) runs it once a second
for a tree somebody is actually looking at, never for the rest.

Three git calls, each chosen for what it does NOT do: `ls-files` reads the
index and walks nothing; `ls-files --others --exclude-standard` walks, but with
`--exclude=<name>` for the directories nobody wants to read — added to git's own
exclude list, so a `node_modules` that some repo forgot to ignore is PRUNED at
the directory and never descended; and `status --porcelain=v2 -z
--untracked-files=no` skips the untracked walk entirely, since the second call
already did it. Porcelain v2 rather than v1 on purpose: `run.git` strips its
output, and a v1 record opens with a SPACE when only the worktree changed.

A file git names but the disk no longer has is dropped, not drawn: the reader
is looking at the disk. The list is CAPPED, and the cap is stated in the answer
(`total` beside `capped`) — a silently short tree is a lie about the project.
"""

from __future__ import annotations

import os
import stat as filemode
from typing import NamedTuple
from pathlib import Path

from . import run

EXCLUDED = frozenset(
    {
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        "dist",
        "build",
        ".cache",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".next",
        ".turbo",
        "coverage",
        "target",
    }
)
"""Directories nobody opens an editor to read. Pruned from the untracked walk
AND filtered from the tracked list — a committed `dist/` is still not code."""

NESTED = ".taskops/trees/"
"""Inside the checkout every worktree is a subdirectory; listing them under
`main` would draw the whole board again inside its first entry."""

FILE_CAP = 4000

CLEAN, MODIFIED, ADDED, STAGED, UNTRACKED = "clean", "modified", "added", "staged", "untracked"
COMMITTED, DELETED = "committed", "deleted"
"""The branch's own half of the WORKING SET: `committed` is clean on the disk
but differs from the base — the file this worktree already wrote and
committed — and `deleted` is gone since the base, listed with no bytes so the
tree can strike it through. A worktree that committed and moved on used to
read as clean, which is the one thing a reader opening it wants to know."""
GONE = "gone"
"""Deleted from the disk and still in the index — dropped from the listing."""


class Entry(NamedTuple):
    path: str
    size: int
    mtime: float
    state: str


class Scan(NamedTuple):
    files: dict[str, Entry]
    capped: bool
    total: int


def take(tree: Path, cap: int = FILE_CAP, base: str = "") -> Scan:
    """The tree as it stands: every project file git can name, measured — and,
    given the base's sha, which of them the branch itself changed."""
    states = _states(tree)
    tracked = set(_tracked(tree))
    named = (tracked | set(_untracked(tree))) - {
        path for path, state in states.items() if state == GONE
    }
    branch, gone = _since(tree, base) if base else (set[str](), set[str]())
    paths = sorted(path for path in named | gone if not excluded(path))
    files: dict[str, Entry] = {}
    for path in paths[:cap]:
        if path in gone and path not in named:
            files[path] = Entry(path, 0, 0.0, DELETED)
            continue
        try:
            found = os.stat(tree / path)
        except OSError:
            continue  # gone between the listing and the stat; the next scan will not name it
        if not filemode.S_ISREG(found.st_mode):
            continue  # a submodule, a socket — nothing a reader opens
        # A path status did not name is clean if the index has it, untracked if not
        # — decided from the two listings already taken, never by a fourth call.
        state = states.get(path, CLEAN if path in tracked else UNTRACKED)
        if state == CLEAN and path in branch:
            state = COMMITTED
        files[path] = Entry(path, found.st_size, found.st_mtime, state)
    return Scan(files, len(paths) > cap, len(paths))


def differs(before: Scan, after: Scan) -> bool:
    """Did anything a reader could see move? Structural, so a touched file with
    the same bytes still counts — its mtime is what the disk reports."""
    return before != after


def excluded(path: str) -> bool:
    return path.startswith(NESTED) or any(part in EXCLUDED for part in path.split("/"))


def _tracked(tree: Path) -> list[str]:
    raw = run.git("ls-files", "-z", cwd=tree)
    return [path for path in raw.out.split("\0") if path] if raw.ok else []


def _untracked(tree: Path) -> list[str]:
    args = ["ls-files", "-z", "--others", "--exclude-standard", f"--exclude={NESTED.rstrip('/')}"]
    args += [f"--exclude={name}" for name in sorted(EXCLUDED)]
    raw = run.git(*args, cwd=tree)
    return [path for path in raw.out.split("\0") if path] if raw.ok else []


def _since(tree: Path, base: str) -> tuple[set[str], set[str]]:
    """(changed, deleted) between the base's sha and HEAD — the branch's own
    work. One `diff --name-status`; a rename names its NEW path as changed."""
    raw = run.git("diff", "--name-status", "-z", base, "HEAD", cwd=tree)
    changed: set[str] = set()
    deleted: set[str] = set()
    if not raw.ok:
        return changed, deleted
    records = iter(raw.out.split("\0"))
    for status in records:
        if not status:
            continue
        path = next(records, "")
        if status[0] in "RC":
            path = next(records, path)  # the new name follows the old one
        (deleted if status[0] == "D" else changed).add(path)
    return changed, deleted


def _states(tree: Path) -> dict[str, str]:
    """Path → state for every TRACKED file that is not clean, from porcelain v2.

    A record is `1 XY … path` for an ordinary change, `2 XY … path\\0orig` for a
    rename (the old name rides in the NEXT record and is skipped), `u XY … path`
    for a conflict. `X` is the index, `Y` the worktree — and the worktree
    decides first, because it is what the reader is looking at."""
    raw = run.git("status", "--porcelain=v2", "-z", "--untracked-files=no", cwd=tree)
    found: dict[str, str] = {}
    if not raw.ok:
        return found
    records = iter(raw.out.split("\0"))
    for record in records:
        kind, _, rest = record.partition(" ")
        if kind == "1":
            fields = rest.split(" ", 7)
            found[fields[7]] = _state(fields[0])
        elif kind == "2":
            fields = rest.split(" ", 8)
            found[fields[8]] = _state(fields[0])
            next(records, None)  # the original path
        elif kind == "u":
            fields = rest.split(" ", 9)
            found[fields[9]] = MODIFIED
    return found


def _state(xy: str) -> str:
    index, tree = xy[0], xy[1]
    if tree == "D":
        return GONE
    if tree == "M":
        return MODIFIED
    if index == "A":
        return ADDED
    if index in "MRC":
        return STAGED
    return UNTRACKED if index == "D" else CLEAN  # `git rm --cached`: on disk, out of the index
