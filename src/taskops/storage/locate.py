"""Finding the project from any path inside it.

Every surface takes a path from someone who was not thinking about where the
project root is — an agent passes its cwd, a git hook passes wherever git ran it,
the studio passes whatever was typed. Walking up for `.taskops/` is what makes all
three the same call, and it is the same convention as `.git` for the same reason.
"""

from __future__ import annotations

import os
from pathlib import Path

from .._errors import NotInitialized

__all__ = ["PROJECT_DIR", "DB_FILE", "LOG_FILE", "GUIDE_FILE", "REPORTS_DIR", "ENV_ROOT",
           "resolve_root", "find_root", "is_project"]

PROJECT_DIR = ".taskops"

DB_FILE = f"{PROJECT_DIR}/db.sqlite"
"""GITIGNORED. Derived state — every row in it can be rebuilt from the log."""

LOG_FILE = f"{PROJECT_DIR}/events.jsonl"
"""COMMITTED. The shared source of truth: append-only, one JSON object per line,
ids that are content hashes. That combination is what lets two developers merge
their agents' work with `git pull` and no server — a conflict needs two writers of
the same line, and appenders never produce one."""

GUIDE_FILE = f"{PROJECT_DIR}/GUIDE.md"
"""The agent-facing manual `taskops init` writes. Read by humans too, which is the
point: one document, so the two cannot be told different things."""


REPORTS_DIR = f"{PROJECT_DIR}/reports"
"""COMMITTED, unlike everything else generated here. A daily dossier is written ONCE and
then narrated by a human or a session — so it stops being derived state the moment somebody
adds a paragraph to it, and a regenerated copy could not carry that paragraph back."""


ENV_ROOT = "TASKOPS_ROOT"
"""Overrides the search entirely. THE mechanism that makes dispatched workers work.

A worker runs in a `git worktree`, which has no `.taskops/` of its own — so walking up would find
either nothing or, worse, some unrelated project further up the filesystem. With this set, N workers
in N worktrees all coordinate through ONE board, which is the whole point of dispatching them.

An override and not a fallback: if it is set and wrong, that is an error worth seeing rather than a
silent walk up to a different project.
"""


def find_root(start: Path | str) -> Path | None:
    """The nearest ancestor holding a `.taskops/` with a LOG in it, or None.

    The log and not the directory, and that distinction is not pedantry: `~/.taskops/` exists
    on every machine that has ever run `taskops login`, because that is where the session file
    lives. Matching on the directory alone made the HOME DIRECTORY a project — so a fresh repo
    anywhere under it resolved its root to `~`, and `taskops init` there "adopted" the home
    directory instead of creating a project. Found the first time somebody made a scratch repo
    in `~/experiments`.

    `$TASKOPS_ROOT` wins outright, and it is checked the same way for the same reason.
    """
    forced = os.environ.get(ENV_ROOT, "").strip()
    if forced:
        candidate = Path(forced).expanduser().resolve()
        return candidate if is_project(candidate) else None
    here = Path(start).expanduser().resolve()
    for candidate in (here, *here.parents):
        if is_project(candidate):
            return candidate
    return None


def is_project(candidate: Path) -> bool:
    """A directory is a project when its `.taskops/` holds the event log.

    The log is the one file every project has and nothing else creates: the cache is
    gitignored and may be absent on a fresh clone, the guide can be deleted, and the reports
    directory only appears once somebody writes one. The log is written by `init` and is the
    thing a project IS.
    """
    return (candidate / LOG_FILE).is_file()


def resolve_root(start: Path | str) -> Path:
    """Same, but a missing project is an error naming the fix.

    Raising rather than creating: `taskops init` also installs git hooks and
    writes the guide, and a store that appeared silently under whatever directory
    an agent happened to be in would be a project nobody knows exists.
    """
    root = find_root(start)
    if root is None:
        raise NotInitialized.at(start)
    return root
