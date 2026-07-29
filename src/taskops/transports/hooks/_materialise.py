"""Session start: copy the project's specialists into `.claude/agents/` so the host can use them.

The registry lives in `.taskops/agents/` because it is a PROJECT fact and travels through git.
Claude Code, though, only invokes what is in `.claude/agents/`. Nothing bridges the two but
this, and it runs on the one event that always happens before anybody could need an agent.

Three rules it may never break, and they are the whole design:

*Only what we wrote.* A file is overwritten or pruned ONLY if it carries `agents.MARKER`. A
hand-written agent in `.claude/agents/` is somebody's work and taskops does not get to delete
it — a coordination tool that eats a developer's files gets uninstalled the same afternoon.

*Never speak, never block.* Same contract as the sweep launch: every failure is swallowed, and
the whole pass is a handful of small file reads, well inside the hook's budget. A session that
would not start because an agent file had a typo is not a trade taskops gets to make.

*Only the specialists.* The plugin's own defaults are already installed by the plugin; copying
them here would shadow them with a stale duplicate the next release could not update.
"""

from __future__ import annotations

from pathlib import Path

from ..._errors import TaskopsError
from ...usecases.agents import MARKER, materialised, specialists

__all__ = ["materialise_agents", "TARGET_DIR"]

TARGET_DIR = ".claude/agents"


def materialise_agents(cwd: str) -> None:
    """Write, refresh and prune. NEVER raises — see the module docstring."""
    try:
        from ...usecases import locate

        _sync(locate(cwd))
    except (TaskopsError, OSError, ValueError):
        return


def _sync(root: Path) -> None:
    specs = specialists(root)
    folder = root / TARGET_DIR
    if not specs and not folder.is_dir():
        return
    folder.mkdir(parents=True, exist_ok=True)
    keep = set()
    for spec in specs:
        path = folder / f"{spec['name']}.md"
        keep.add(path.name)
        _write(path, materialised(spec))
    _prune(folder, keep)


def _write(path: Path, text: str) -> None:
    """Idempotent: an unchanged file is not touched, so its mtime stays honest and a watcher
    does not see every session as a change."""
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == text:
            return
        if MARKER not in current:
            return
    path.write_text(text, encoding="utf-8")


def _prune(folder: Path, keep: set[str]) -> None:
    """Delete OUR leftovers only. An agent removed from the registry must stop being offered,
    or a rename leaves the old specialist invokable forever."""
    for path in folder.glob("*.md"):
        if path.name in keep:
            continue
        try:
            if MARKER in path.read_text(encoding="utf-8"):
                path.unlink()
        except (OSError, UnicodeDecodeError):
            continue
