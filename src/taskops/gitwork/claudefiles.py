"""The assistant's own config files — `.mcp.json` and `.claude/settings.json`.

Split out of `install.py` at its own seam: that file writes what GIT needs
(hooks, gitignore, the board address), this one what CLAUDE reads. Both are
merged, never clobbered — these files are the user's, not ours.

One Claude hook, and exactly one, since 2026-08-06 (MENTIONS.md §9). It reads
the board and injects a line; it decides nothing and stores nothing, so deleting
it costs immediacy and nothing else. What stays banned is the v1 shape: a hook
that held state, gated an action, or was a second place where truth lived.
"""

from __future__ import annotations

import json
from pathlib import Path

from .._json import as_rows, as_object

# `taskops hook claude`, wired on the events that bracket a turn: every tool
# call (so a worker mid-edit is reached) and the prompt (so the human is).
CLAUDE_EVENTS = ("PostToolUse", "UserPromptSubmit")

MODULE = "-m taskops.cli hook claude"
"""What makes a hook entry OURS, whatever interpreter it names.

JSON has no comments, so there is no marker to write — the command is the
marker (`write_mcp` gets a named key for free; a hooks array has nothing but
its contents). Recognising ours by the MODULE and not by the whole string is
the fix for a real duplicate: install once from a project venv and again from
the uv tool and the two commands differ only in their python, so both survived
and the hook fired twice per tool call, forever. Ours is replaced in place;
somebody else's is still never touched."""


def claude_command(python: str) -> str:
    return f'"{python}" {MODULE}'


def write_claude_hooks(repo: Path, python: str) -> list[str]:
    """Merge the delivery hook into `.claude/settings.json`, never clobbering.

    Same contract as `write_mcp` and for the same reason: this file is the
    user's, not ours. Somebody else's hooks stay, and a second `join` — even
    from a DIFFERENT interpreter — replaces our entry instead of adding one.

    `PostToolUse` carries no matcher restriction on purpose — the gap this
    closes is a worker twenty minutes deep in Edit and Bash calls, so narrowing
    to a tool family would reopen it for every other tool.
    """
    path = repo / ".claude" / "settings.json"
    settings: dict[str, object] = {}
    if path.exists():
        try:
            settings = as_object(json.loads(path.read_text(encoding="utf-8")))
        except ValueError:
            settings = {}  # a broken file is replaced, never merged into blindly
    command = claude_command(python)
    hooks = as_object(settings.get("hooks"))
    added: list[str] = []
    for event in CLAUDE_EVENTS:
        kept = [e for e in as_rows(hooks.get(event)) if not _ours(e)]
        already = len(kept) < len(as_rows(hooks.get(event)))
        entry: dict[str, object] = {"hooks": [{"type": "command", "command": command}]}
        if event == "PostToolUse":
            entry["matcher"] = "*"  # every tool — "" and an absent key mean the same
        hooks[event] = [*kept, entry]
        if not already:
            added.append(event)
    settings["hooks"] = hooks
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return added


def _ours(entry: dict[str, object]) -> bool:
    """One of our entries, whichever python it was written with."""
    return any(MODULE in str(h.get("command", "")) for h in as_rows(entry.get("hooks")))


def write_mcp(repo: Path, python: str, actor: str) -> None:
    """Merge into an existing `.mcp.json` — never replace somebody's other servers."""
    path = repo / ".mcp.json"
    config: dict[str, object] = {}
    if path.exists():
        try:
            config = as_object(json.loads(path.read_text(encoding="utf-8")))
        except ValueError:
            config = {}  # a broken file is replaced, never merged into blindly
    servers = as_object(config.get("mcpServers"))
    servers["taskops"] = {
        "command": python,
        "args": ["-m", "taskops.mcp"],
        "env": {"TASKOPS_ACTOR": actor},
    }
    config["mcpServers"] = servers
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
