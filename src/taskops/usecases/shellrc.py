"""The shell's rc file, and the one marked block taskops is allowed to own in it.

This writes to a file the user owns and reads on every login, which makes it the most invasive
thing in the package. Three rules, all of them load-bearing:

*One block, marked at both ends.* Re-running rewrites what is between the markers and never
appends a second copy — the same discipline `install_hooks` uses on `.git/hooks`, for the same
reason: a tool that leaves a trail of stanzas gets uninstalled by hand, badly.

*Nothing is written without being shown.* `--print` renders the exact block and the exact path
and touches nothing. A CLI that edits `~/.zshrc` on a verb somebody typed to see what it does
has spent trust it cannot earn back.

*Removable.* Whatever this writes, `--remove` takes out, leaving the file as if taskops had
never run. An installer with no uninstaller is a guest that moved in.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

__all__ = ["OPEN", "CLOSE", "rc_path", "alias_line", "block", "install_alias", "remove_alias",
           "claude_binaries"]

OPEN = "# >>> taskops >>>"
CLOSE = "# <<< taskops <<<"

CHANNEL_FLAG = "--dangerously-load-development-channels server:taskops-channel"
"""What the alias adds. The flag is a mouthful on purpose — Claude Code is telling you that a
development channel is not sandboxed — and an alias is the honest way to stop retyping it
without pretending it is not there."""


def rc_path(shell: str = "") -> Path:
    """Where THIS user's interactive shell reads its configuration.

    `$SHELL` and not the parent process: a script run from a Makefile has a parent of `sh` and
    a user who has never seen it, and writing an alias into `~/.profile` because of that would
    be a file nobody looks at.

    bash on macOS is the case worth spelling out: Terminal.app starts LOGIN shells, which read
    `.bash_profile` and never `.bashrc` — the single most common reason an alias "did not
    work". So the profile wins there when it exists.
    """
    name = Path(shell or os.environ.get("SHELL", "")).name
    if name == "fish":
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
        return base / "fish" / "config.fish"
    if name == "zsh":
        return Path(os.environ.get("ZDOTDIR") or Path.home()) / ".zshrc"
    if name == "bash":
        profile = Path.home() / ".bash_profile"
        if sys.platform == "darwin" and profile.is_file():
            return profile
        return Path.home() / ".bashrc"
    return Path.home() / f".{name}rc" if name else Path.home() / ".profile"


def claude_binaries() -> list[str]:
    """Every `claude*` on PATH, so the prompt offers what this machine actually has.

    Not used to CHOOSE any more — `$TASKOPS_CLAUDE` decides that at run time — but still worth
    printing, because somebody who has two of these wants to be told the var exists.
    """
    seen: dict[str, None] = {}
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        if not folder:
            continue
        try:
            entries = sorted(Path(folder).iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.name.startswith("claude") and shutil.which(entry.name):
                seen.setdefault(entry.name, None)
    return list(seen)


ENV_CLAUDE = "TASKOPS_CLAUDE"
"""The env var the alias defers to, so which claude it runs is decided WHEN IT RUNS.

Setup used to ask, and baking the answer into a line in a startup file is the wrong place for
it: a machine with `claude` and `claude-jp` on it has two accounts, and which one you want
depends on the terminal you are in — not on what you happened to answer the day you installed
this. `export TASKOPS_CLAUDE=claude-jp` in a work shell, and the same alias follows."""


def alias_line(name: str, command: str = "", *, shell: str = "") -> str:
    """The alias, in the syntax the shell in question actually parses.

    It defers to `$TASKOPS_CLAUDE` and falls back to plain `claude`, so nothing is decided at
    install time. `command` overrides that entirely for somebody who wants a fixed binary
    written down — a per-project rc, a machine with one account and no interest in the var.

    fish is spelled separately, and not for tidiness: it has no `=` in `alias` and no
    `${VAR:-default}`, so a POSIX line in `config.fish` fails at every new terminal with an
    error most people blame on whatever they installed last.
    """
    if Path(shell or os.environ.get("SHELL", "")).name == "fish":
        runs = command or f"(test -n \"${ENV_CLAUDE}\"; and echo ${ENV_CLAUDE}; or echo claude)"
        return f"alias {name} '{runs} {CHANNEL_FLAG}'"
    runs = command or f"${{{ENV_CLAUDE}:-claude}}"
    return f"alias {name}=\"{runs} {CHANNEL_FLAG}\""


def block(name: str, command: str, *, shell: str = "") -> str:
    """The whole stanza, markers included — what `--print` shows and what gets written."""
    return "\n".join([
        OPEN,
        "# taskops board channel: board events arrive inside the session.",
        "# Remove this block, or run `taskops setup --remove`.",
        alias_line(name, command, shell=shell),
        CLOSE,
    ]) + "\n"


def install_alias(path: Path, stanza: str) -> bool:
    """Write the block, replacing our own if it is there. True when the file changed.

    Returns False on an unchanged file rather than rewriting it: an untouched mtime is what
    tells the next reader that nothing happened, and a backup file per no-op run is litter.
    """
    current = path.read_text(encoding="utf-8") if path.is_file() else ""
    updated = _without(current) + ("\n" if _without(current).strip() else "") + stanza
    if current == updated:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated, encoding="utf-8")
    return True


def remove_alias(path: Path) -> bool:
    """Take the block out. True when there was one."""
    if not path.is_file():
        return False
    current = path.read_text(encoding="utf-8")
    stripped = _without(current)
    if stripped == current:
        return False
    path.write_text(stripped, encoding="utf-8")
    return True


def _without(text: str) -> str:
    """The file minus our block. Everything outside the markers survives byte for byte."""
    if OPEN not in text or CLOSE not in text:
        return text
    head, _, rest = text.partition(OPEN)
    _, _, tail = rest.partition(CLOSE)
    return (head.rstrip("\n") + "\n" + tail.lstrip("\n")).lstrip("\n")
