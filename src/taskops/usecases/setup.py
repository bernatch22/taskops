"""`taskops init` — making a repository coordinated.

Four things, and the order is deliberate: the project directory, the gitignore entry, the
project's Claude Code wiring (`.mcp.json` + `.claude/settings.json`), then the git hooks. If hook installation fails the project still works — every hook here
is an optimisation of something the MCP tools already do — so a partial init leaves a
usable system rather than a broken one.

Existing hooks are CHAINED, never overwritten. A repository's `post-commit` may already
run a linter somebody depends on, and a coordination tool that silently deleted it would
deserve everything that followed.
"""

from __future__ import annotations

from pathlib import Path

from .._errors import BadRequest
from ..storage import GUIDE_FILE, LOG_FILE, PROJECT_DIR, Store, find_root
from ._gitignore import ignore
from .claudefile import wire_hooks
from .hooks import install_hooks
from .mcpfile import wire_mcp

__all__ = ["init", "InitReport"]

_GUIDE_SOURCE = Path(__file__).resolve().parents[1] / "assets" / "GUIDE.md"

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
    _refuse_home(root, created)
    (root / PROJECT_DIR).mkdir(parents=True, exist_ok=True)
    ignore(root)
    _guide(root)
    (root / LOG_FILE).touch(exist_ok=True)
    _specialists(root)
    wire_mcp(root)      # the project's own file, merged — see `mcpfile`
    wire_hooks(root)    # and the Claude Code hooks, for the same reason and the same way
    adopted = _adopt(root)
    hooks, skipped = install_hooks(root) if install_git_hooks else ([], [])
    return InitReport(root=root, created=created, hooks=hooks, skipped=skipped,
                      adopted=adopted)


def _refuse_home(root: Path, created: bool) -> None:
    """Never turn somebody's HOME into a project by accident.

    `~` holds `.taskops/sessions.json`, so it is one `mkdir` away from looking like a board —
    and a board rooted at the home directory would quietly answer for every repository under
    it that has not been initialised. Nobody means this, and the one person who does can pass
    `$TASKOPS_ROOT`.
    """
    if created and root == Path.home().resolve():
        raise BadRequest(
            f"{root} is your home directory, not a project — `cd` into the repository first. "
            f"(`~/.taskops/` already exists because your login session lives there.)")


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


def _specialists(root: Path) -> None:
    """Write our sub-agents into `.claude/agents/`, OVERWRITING ours every init.

    The third rendering of the same failure, closed at the pattern this time. `.mcp.json` was
    missing (specialists spawned with no tools), the Claude hooks were missing (sessions never
    learned their role), and then `Agent type 'taskops-worker' not found` — because the agents
    lived in a plugin nobody installs. Worse, by then the SessionStart injection was ORDERING
    sessions to dispatch a specialist that did not exist; every one fell back to
    `general-purpose`, and a verifier without the sonnet/read-only constraints spent twenty
    minutes building venvs to check three calendar functions.

    Same discipline as GUIDE.md: these ship with the package and describe THIS version's
    tools, so ours are overwritten on every init and stay in step — while any agent the
    project defined itself is untouched, because only files named taskops-* are ours. This is
    not the mirrored-directory bug (`CLAUDE.md` carries the scar): there is no second registry
    and no translation — the package is the source, `.claude/agents/` is the one place Claude
    Code reads, and a test pins the plugin's copies to these bytes.
    """
    source = Path(__file__).resolve().parents[1] / "assets" / "agents"
    if not source.is_dir():
        return
    destination = root / ".claude" / "agents"
    destination.mkdir(parents=True, exist_ok=True)
    for spec in sorted(source.glob("taskops-*.md")):
        (destination / spec.name).write_text(spec.read_text(encoding="utf-8"),
                                             encoding="utf-8")


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
