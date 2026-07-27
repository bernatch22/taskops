"""`taskops init` — making a repository coordinated.

Three things, and the order is deliberate: the project directory, the gitignore entry,
then the git hooks. If hook installation fails the project still works — every hook here
is an optimisation of something the MCP tools already do — so a partial init leaves a
usable system rather than a broken one.

Existing hooks are CHAINED, never overwritten. A repository's `post-commit` may already
run a linter somebody depends on, and a coordination tool that silently deleted it would
deserve everything that followed.
"""

from __future__ import annotations

from pathlib import Path

from ..storage import GUIDE_FILE, LOG_FILE, PROJECT_DIR, Store, find_root
from .hooks import install_hooks

__all__ = ["init", "InitReport"]

_GUIDE_SOURCE = Path(__file__).resolve().parents[1] / "assets" / "GUIDE.md"

_MARKER = "# taskops"
_GITIGNORE = f"""
{_MARKER} — the database is a CACHE, rebuildable from events.jsonl
{PROJECT_DIR}/db.sqlite
{PROJECT_DIR}/db.sqlite-wal
{PROJECT_DIR}/db.sqlite-shm
"""


class InitReport:
    """What init actually did, so the CLI can report it instead of claiming success."""

    def __init__(self, *, root: Path, created: bool, hooks: list[str],
                 skipped: list[str]) -> None:
        self.root = root
        self.created = created
        self.hooks = hooks
        self.skipped = skipped


def init(start: Path | str, *, install_git_hooks: bool = True) -> InitReport:
    """Create `.taskops/`, ignore the cache, install the hooks. Idempotent.

    Re-running is safe and is the supported way to repair a project whose hooks were
    lost — which happens on every fresh clone, because `.git/hooks` is not tracked.
    """
    root = Path(start).expanduser().resolve()
    existing = find_root(root)
    created = existing is None
    root = existing or root
    (root / PROJECT_DIR).mkdir(parents=True, exist_ok=True)
    _ignore(root)
    _guide(root)
    (root / LOG_FILE).touch(exist_ok=True)
    with Store(root):
        pass                    # opening applies the schema; nothing else to do here
    hooks, skipped = install_hooks(root) if install_git_hooks else ([], [])
    return InitReport(root=root, created=created, hooks=hooks, skipped=skipped)


def _guide(root: Path) -> None:
    """Copy the agent-facing manual into the project, OVERWRITING it every init.

    Overwriting on purpose, unlike `.gitignore`: this file ships with the package and
    describes what this version of the tools actually does. A stale copy that survived an
    upgrade would be a document telling agents to use a rule that no longer exists — and
    since it is committed, everyone on the team would read the wrong one. Anything a project
    wants to add about its own conventions belongs in CLAUDE.md, which taskops never touches.
    """
    destination = root / GUIDE_FILE
    if _GUIDE_SOURCE.is_file():
        destination.write_text(_GUIDE_SOURCE.read_text(encoding="utf-8"),
                               encoding="utf-8")


def _ignore(root: Path) -> None:
    """Add the cache to `.gitignore`, once.

    Matched on the marker rather than on the paths: a developer may reformat those
    lines, and appending a duplicate block on every init is how a `.gitignore` becomes
    forty lines of the same thing.
    """
    path = root / ".gitignore"
    current = path.read_text(encoding="utf-8") if path.is_file() else ""
    if _MARKER in current:
        return
    separator = "" if current.endswith("\n") or not current else "\n"
    path.write_text(current + separator + _GITIGNORE, encoding="utf-8")
