"""What `taskops join` writes into a project. Three hooks, five small files.

    .git/hooks/prepare-commit-msg   stamp the trailer      (never refuses)
    .git/hooks/post-commit          bind + push the branch (never blocks)
    .taskops/board.json             the address — COMMITTED, it travels with the code
    .taskops/remote.json            the credential — 0600, gitignored, never travels
    .mcp.json + .claude/settings.json   Claude's own files — `claudefiles.py`,
                                        this file's sibling, merged the same way

One Claude hook, and exactly one, since 2026-08-06. It reads
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
from typing import Any
from pathlib import Path

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


def write_config(  # noqa: PLR0913 — one config file, one writer; the fields are the file
    repo: Path, url: str, token: str, login: dict[str, str] | None = None,
    expires: float = 0.0, readonly: bool = False,
) -> None:
    """board.json is public, remote.json is not — and the modes say so.

    `login` is what makes remote.json a SESSION CACHE rather than a pasted secret:
    the host, the principal and the key that can mint the next token with nobody
    watching (`session.py`). Absent, this is the join every board did before the
    keys existed and the token is a standing one — milestone rule 3.

    `readonly` is the VIEWER's join (`cli/watch.py`): a public board, no token
    minted. RECORDED, not inferred from an empty token — "no token" is also what
    a BROKEN join leaves, and one is a window, the other a bug (`board.py`).
    """
    folder = repo / ".taskops"
    folder.mkdir(parents=True, exist_ok=True)
    address: dict[str, Any] = {"url": url}
    if readonly:
        address["readonly"] = True
    (folder / "board.json").write_text(json.dumps(address, indent=2) + "\n", encoding="utf-8")
    secret = folder / "remote.json"
    body: dict[str, Any] = {"token": token}
    if login:
        body["login"], body["token_expires"] = login, expires
    secret.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
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
