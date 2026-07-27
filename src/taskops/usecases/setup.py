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
{_MARKER} — commit events.jsonl and NOTHING else under {PROJECT_DIR}/
{PROJECT_DIR}/db.sqlite
{PROJECT_DIR}/db.sqlite-wal
{PROJECT_DIR}/db.sqlite-shm
{PROJECT_DIR}/GUIDE.md
"""
"""Why GUIDE.md is ignored rather than committed, which looks wrong at first.

It is GENERATED: it ships inside the package and `_guide` rewrites it on every init, so it always
describes the version of taskops that is actually installed. Tracking a file that a command
overwrites would leave `git status` dirty after every init, and two developers on different taskops
versions would fight over its contents forever.

It also removes a real merge conflict. Following the usage guide end to end, two clones that each
ran `taskops init` could not `git pull` from one another — git refused, because the incoming commit
carried files both sides had independently created untracked. Anything generated belongs on this
side of the line.
"""


class InitReport:
    """What init actually did, so the CLI can report it instead of claiming success."""

    def __init__(self, *, root: Path, created: bool, hooks: list[str],
                 skipped: list[str], adopted: int = 0) -> None:
        self.root = root
        self.created = created
        self.hooks = hooks
        self.skipped = skipped
        self.adopted = adopted
        """Tasks materialised from a log that was already in the working tree.

        Non-zero on a FRESH CLONE, which is the case this exists for. Following the usage guide
        end to end, a teammate cloned, ran `taskops init`, and saw an empty board: the log was
        sitting right there in the checkout and nothing had read it. Now init reads it.
        """


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
    adopted = _adopt(root)
    hooks, skipped = install_hooks(root) if install_git_hooks else ([], [])
    return InitReport(root=root, created=created, hooks=hooks, skipped=skipped,
                      adopted=adopted)


def _adopt(root: Path) -> int:
    """Open the database (which applies the schema) and read whatever log is already here.

    THE fresh-clone step, and it was missing: a teammate cloned a repository whose checkout
    carried the whole event log, ran `taskops init`, and saw an empty board — the log was sitting
    right there and nothing had read it. Adoption is just an import+replay, both idempotent, so on
    a brand-new project this is a no-op and on a re-run it changes nothing.
    """
    from ..engine import replay, unblock
    from ..storage import import_events

    with Store(root) as store:
        applied = replay.apply(store, import_events(store))
        unblock(store)
        return applied


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
