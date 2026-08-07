"""What `taskops join` writes into a project. Three hooks, five small files.

    .git/hooks/prepare-commit-msg   stamp the trailer      (never refuses)
    .git/hooks/post-commit          bind + push the branch (never blocks)
    .taskops/board.json             the address — COMMITTED, it travels with the code
    .taskops/remote.json            the credential — 0600, gitignored, never travels
    .mcp.json                       the MCP server, merged into whatever is there
    .claude/settings.json           the DELIVERY hook, merged the same way

One Claude hook, and exactly one, since 2026-08-06 (MENTIONS.md §9). It reads
the board and injects a line; it decides nothing and stores nothing, so deleting
it costs immediacy and nothing else. What stays banned is the v1 shape: a hook
that held state, gated an action, or was a second place where truth lived.

No agent files. No local database pretending to be a backup of a remote board.
The address travels with the repo; the secret never does.
"""

from __future__ import annotations

import os
import json
import stat
from pathlib import Path

from .._json import as_rows, as_object

HOOKS = ("prepare-commit-msg", "post-commit")
MARK = "# taskops v2 hook — regenerate with: taskops join <url>"

# Everything under `.taskops/` that is this machine's and not the project's.
IGNORED = (
    ".taskops/remote.json",
    ".taskops/pending.jsonl",
    ".taskops/trees/",
    ".taskops/hook-seen.json",  # the delivery hook's per-actor throttle stamps
    ".taskops/ui.json",  # the local dashboard's port and token — this machine's
)

# `taskops hook claude`, wired on the two events that bracket a turn: every tool
# call (so a worker mid-edit is reached) and the prompt (so the human is).
CLAUDE_EVENTS = ("PostToolUse", "UserPromptSubmit")

SCRIPTS = {
    # stderr stays visible on purpose: a broken hook must be seen at the first
    # commit, not discovered a week later (v1 sent both streams to /dev/null).
    "prepare-commit-msg": """#!/bin/sh
{mark}
"{python}" -m taskops.cli hook trailer "$@" || true
exit 0
""",
    "post-commit": """#!/bin/sh
{mark}
"{python}" -m taskops.cli hook commit || true
exit 0
""",
}


def install_hooks(repo: Path, python: str) -> list[str]:
    """Write both hooks, executable. An existing foreign hook is left alone."""
    written: list[str] = []
    hooks = repo / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    for name in HOOKS:
        path = hooks / name
        if path.exists() and MARK not in path.read_text(encoding="utf-8"):
            written.append(f"{name} (kept: not ours)")
            continue
        path.write_text(SCRIPTS[name].format(mark=MARK, python=python), encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
        written.append(name)
    return written


def write_config(repo: Path, url: str, token: str) -> None:
    """board.json is public, remote.json is not — and the modes say so."""
    folder = repo / ".taskops"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "board.json").write_text(json.dumps({"url": url}, indent=2) + "\n", encoding="utf-8")
    secret = folder / "remote.json"
    secret.write_text(json.dumps({"token": token}, indent=2) + "\n", encoding="utf-8")
    os.chmod(secret, 0o600)


def write_gitignore(repo: Path) -> bool:
    """Append the entries that are MISSING, one by one.

    Line by line rather than all-or-nothing: the old check asked whether the
    block had ever been written and skipped the whole thing if it had, so a repo
    joined before a new entry existed never got it — and the first new entry
    (the hook's throttle stamp) would have been committed by everybody who
    joined before today.
    """
    path = repo / ".gitignore"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    have = {line.strip() for line in existing.splitlines()}
    missing = [entry for entry in IGNORED if entry not in have]
    if not missing:
        return False
    joiner = "" if existing.endswith("\n") or not existing else "\n"
    header = "" if "# taskops" in have else "# taskops\n"
    path.write_text(existing + joiner + "\n" + header + "\n".join(missing) + "\n", encoding="utf-8")
    return True


def claude_command(python: str) -> str:
    """The one string that identifies this hook as ours. JSON has no comments,
    so there is no marker to write — the command IS the marker (`write_mcp` gets
    a named key for free; a hooks array has nothing but its contents)."""
    return f'"{python}" -m taskops.cli hook claude'


def write_claude_hooks(repo: Path, python: str) -> list[str]:
    """Merge the delivery hook into `.claude/settings.json`, never clobbering.

    Same contract as `write_mcp` and for the same reason: this file is the
    user's, not ours. Somebody else's hooks stay, a second `join` adds nothing,
    and the only thing we look for is our own command string.

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
        entries = as_rows(hooks.get(event))
        if any(command == h.get("command") for e in entries for h in as_rows(e.get("hooks"))):
            continue  # already ours: joining twice is a no-op, not a duplicate
        entry: dict[str, object] = {"hooks": [{"type": "command", "command": command}]}
        if event == "PostToolUse":
            entry["matcher"] = "*"  # every tool — "" and an absent key mean the same
        entries.append(entry)
        hooks[event] = entries
        added.append(event)
    if added:
        settings["hooks"] = hooks
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return added


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
