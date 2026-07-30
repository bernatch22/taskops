"""`.claude/settings.json` — the hooks, wired into the PROJECT rather than into a plugin.

The sibling of `mcpfile`, written after the failure that made it necessary. Two developers
joined a board, worked it, and both left their cards dead in `review`. The three hooks that
exist to prevent exactly that had never run: hooks ship in the taskops PLUGIN, the plugin was
not installed, and nothing anywhere said so. They had the MCP tools (from `.mcp.json`, which
`init` writes) and the git hooks (from `.git/hooks`, which `init` installs) — so the setup
looked complete and was silently missing its whole feedback loop.

A plugin is the wrong home for this. It is a per-MACHINE, per-person install, and what these
hooks belong to is the PROJECT: joining a board is what should turn a checkout into one where
sessions know their role and cannot end a turn on a review nobody picked up. Same file, same
merge discipline, same reasoning as `.mcp.json` — a repository's settings are shared config,
so this only ever ADDS, and a hook somebody wrote by hand survives untouched.

The plugin still exists and still carries these; a project that has both simply runs them
twice, and every one of them is idempotent by design.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .mcpfile import _read, hook_binary

__all__ = ["SETTINGS_FILE", "wire_hooks", "hooks_for"]

SETTINGS_FILE = ".claude/settings.json"

_EVENTS: dict[str, str] = {
    "PreToolUse": "pre-tool-use",
    "PostToolUse": "post-tool-use",
    "SessionStart": "session-start",
    "Stop": "stop",
    "SubagentStop": "subagent-stop",
}
"""The Claude Code event -> the `taskops-hook` subcommand. Kept as data so `plugin/hooks.json`
and this file are two renderings of one list rather than two lists that drift."""

_MATCHERS = {"PreToolUse": "Bash", "PostToolUse": "Edit|Write|Bash|NotebookEdit"}
"""Only two events filter by tool. The rest fire once per lifecycle moment and a matcher on
them would be a filter over a set of one."""


def hooks_for() -> dict[str, Any]:
    """The five entries taskops installs, with an interpreter that exists.

    `taskops-hook` is resolved to an ABSOLUTE path for the same reason `.mcp.json` resolves
    the interpreter: the hook runs from a cwd nobody chose, under whatever PATH the app was
    launched with, and a bare name that works in your shell has already failed in a GUI-
    launched session twice.
    """
    binary = hook_binary()
    return {event: [{**({"matcher": _MATCHERS[event]} if event in _MATCHERS else {}),
                     "hooks": [{"type": "command", "command": f"{binary} {verb}"}]}]
            for event, verb in _EVENTS.items()}


def wire_hooks(root: Path) -> list[str]:
    """Add the missing hook events to `.claude/settings.json`. Returns the ones it added.

    An event somebody already configured is left ALONE, entry for entry — including one that
    runs taskops differently on purpose. Re-running adds nothing, which is what makes this
    safe to call from every `init`.
    """
    path = root / SETTINGS_FILE
    config = _read(path)
    hooks: dict[str, Any] = config.setdefault("hooks", {})
    added = [event for event, entry in hooks_for().items()
             if event not in hooks and not hooks.__setitem__(event, entry)]
    if added:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return added
