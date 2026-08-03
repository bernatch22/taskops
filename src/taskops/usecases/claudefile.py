"""`.claude/settings.json` — the hooks, wired into the PROJECT rather than into a plugin.

The sibling of `mcpfile`, written after the failure that made it necessary. Two developers
joined a board, worked it, and both left their cards dead in `review`. The three hooks that
exist to prevent exactly that had never run: hooks ship in the taskops PLUGIN, the plugin was
not installed, and nothing anywhere said so. They had the MCP tools (from `.mcp.json`, which
`init` writes) and the git hooks (from `.git/hooks`, which `init` installs) — so the setup
looked complete and was silently missing its whole feedback loop.

A plugin is the wrong home for this. It is a per-MACHINE, per-person install, and what these
hooks belong to is the PROJECT: joining a board is what should turn a checkout into one where
sessions know their role and cannot end a turn on a review nobody picked up. Same merge
discipline as `.mcp.json` — it only ever ADDS, and a hook somebody wrote by hand survives
untouched — but a different FILE, for the reason under `SETTINGS_FILE`.

The plugin still exists and still carries these; a project that has both simply runs them
twice, and every one of them is idempotent by design.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .mcpfile import _read, cli_binary, hook_binary

__all__ = ["SETTINGS_FILE", "wire_hooks", "hooks_for", "statusline_for"]

SETTINGS_FILE = ".claude/settings.local.json"
"""The PERSONAL project settings, not the shared ones, and the reason is one line of output:

    "command": "/Users/berna/.local/share/uv/tools/taskops-cli/bin/taskops-hook session-start"

That path is where `taskops-hook` lives on THIS machine. Committing it would hand every
teammate a hook pointing into a directory they do not have — five broken hooks and no error
anybody would connect to the cause. `settings.local.json` is the file Claude Code reads for
exactly this and the one projects already gitignore; `init` adds it to the block, so a clone
that runs `join` writes its own.
"""

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


def statusline_for() -> dict[str, Any]:
    """The bottom row: `taskops statusline`, reading the session JSON Claude Code pipes to it.

    No `refreshInterval`. Claude Code re-runs a status line on every tool call, prompt and
    permission change, debounced at 300 ms, and everything this bar shows changes because
    something in this session did — a claim, a handover, a message arriving on a tool call. A
    timer on top would re-read sqlite while a person types and move nothing on the screen.

    The one thing it would buy is a teammate's move on a SHARED board landing without a local
    command first, and the bar already tells the truth about that: it says `cached`.
    """
    return {"type": "command", "command": f"{cli_binary()} statusline"}


def wire_hooks(root: Path) -> list[str]:
    """Add the missing hook events and the status line to `.claude/settings.json`.

    Returns what it added. An event somebody already configured is left ALONE, entry for entry
    — including one that runs taskops differently on purpose — and so is a `statusLine`, which
    is somebody's own bar and the last thing a task tool should take over. Re-running adds
    nothing, which is what makes this safe to call from every `init`.
    """
    path = root / SETTINGS_FILE
    config = _read(path)
    hooks: dict[str, Any] = config.setdefault("hooks", {})
    added = [event for event, entry in hooks_for().items()
             if event not in hooks and not hooks.__setitem__(event, entry)]
    if "statusLine" not in config:
        config["statusLine"] = statusline_for()
        added.append("statusLine")
    if added:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return added
