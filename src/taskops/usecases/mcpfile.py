"""`.mcp.json` — the project's MCP servers, written with an interpreter that exists.

The line `python3 -m taskops.transports.mcp` has broken twice in this project's short life, in
two different files, for the same reason: it depends on whichever `python3` is first on PATH
having taskops importable, and it is not — not for pipx, not for uv, not for anybody with
pyenv. The failure is silent on one side (no MCP tools, so a specialist spawns with Read and
Bash and cannot claim its card) and a ModuleNotFoundError at every session start on the other.

So the interpreter is `sys.executable`: the one that is running right now, which by definition
has taskops importable, because it is importing this line.

MERGED, never replaced. A repository's `.mcp.json` is shared config — somebody else's server
lives there — and a tool that rewrote the file would delete a teammate's work to add its own.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

__all__ = ["MCP_FILE", "wire_mcp", "servers_for", "port_for"]

MCP_FILE = ".mcp.json"


def servers_for(root: Path) -> dict[str, Any]:
    """The two servers taskops offers, as `.mcp.json` entries.

    Every path here is ABSOLUTE, and that is not tidiness. A relative path in a config file is
    resolved against the cwd of whoever READS it, and the reader is an MCP server Claude Code
    spawned from somewhere neither of us chose. Written as `.` — the default `--repo` — the
    channel started `taskops ui --repo .`, served a completely different repository, found the
    port already taken and attached to that instead. Two symptoms, one relative path.

    The channel is included even though it needs `--dangerously-load-development-channels` to
    register: naming it here is what makes that flag work at all, and a project that never
    turns it on pays nothing for the entry.
    """
    here = root.expanduser().resolve()
    channel = Path(__file__).resolve().parents[3] / "plugin" / "channel" / "server.ts"
    servers: dict[str, Any] = {
        "taskops": {"command": sys.executable, "args": ["-m", "taskops.transports.mcp"]},
    }
    if channel.is_file():
        servers["taskops-channel"] = {
            "command": "bun", "args": [str(channel)],
            "env": {"TASKOPS_REPO": str(here), "TASKOPS_BIN": _binary(),
                    # A PORT PER PROJECT, derived from the path. Two boards cannot share 2140:
                    # the second channel to start finds the first one's UI listening, attaches
                    # to it, and quietly serves somebody else's board — which is exactly what
                    # happened. Derived rather than random so it is stable across restarts, and
                    # high so it cannot collide with something a developer already runs.
                    "TASKOPS_UI_PORT": str(port_for(here))}}
    return servers


def port_for(root: Path) -> int:
    """A stable port for this project: 2140 for the first one, then derived from the path.

    `sha256` and not `hash()`: Python's is salted per process, so the same checkout would get a
    different port every session and every channel would spawn a UI beside the last one's.
    """
    digest = hashlib.sha256(str(root).encode("utf-8")).digest()
    return 20000 + int.from_bytes(digest[:2], "big") % 20000


def wire_mcp(root: Path) -> list[str]:
    """Add what is missing to `.mcp.json`. Returns the server names it added.

    Only ADDS: an entry somebody already has stays exactly as they wrote it, including one
    named `taskops` pointing somewhere deliberate. Re-running is safe and adds nothing.
    """
    path = root / MCP_FILE
    config = _read(path)
    servers = config.setdefault("mcpServers", {})
    added = [name for name, entry in servers_for(root).items()
             if name not in servers and not servers.__setitem__(name, entry)]
    if added:
        path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return added


def _binary() -> str:
    """The `taskops` console script beside this interpreter, or the bare name.

    The bare name is the honest fallback: a global install has it on PATH, and a checkout that
    somehow does not is a case where naming a path that is not there would be worse.
    """
    beside = Path(sys.executable).with_name("taskops")
    return str(beside) if beside.is_file() else "taskops"


def _read(path: Path) -> dict[str, Any]:
    """What is on disk, or an empty config. A file we cannot parse is left ALONE — refusing to
    write beats truncating somebody's hand-edited JSON because a comma was missing."""
    if not path.is_file():
        return {}
    try:
        parsed: Any = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as err:
        raise ValueError(f"{path} is not valid JSON — fix it, or move it aside: {err}") from err
    return parsed if isinstance(parsed, dict) else {}
