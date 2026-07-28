"""`taskops status` squeezed into one shell-prompt segment, and its machine twin.

    tk:taskops 3▸1 ⇡5 !r

Three facts and a warning: open cards, how many are MINE, events this machine has not
pushed, and `!r` when yesterday was never narrated. Everything else `status` knows is
deliberately dropped — a prompt segment competes for the same row as the branch name and
the exit code, so anything that does not change how the next command is chosen is noise.

EVERY segment disappears when it is zero, and a project with nothing to say renders as the
EMPTY STRING rather than as `tk:name`. A prompt that always shows something trains the eye
to stop reading it, which costs more than the segment was ever worth.

Colour is a PARAMETER and the default is NONE, because the two consumers escape colour
differently: zsh wants `%F{cyan}` inside `PROMPT` (raw SGR there miscounts the line width
and corrupts editing), while Claude Code's statusline takes ANSI. Plain is the only answer
that is never wrong, so it is the one you get unless you ask.
"""

from __future__ import annotations

from .._types import OPEN_STATUSES
from ..contracts.status import Status

__all__ = ["render_prompt", "render_porcelain", "PORCELAIN_VERSION"]

PORCELAIN_VERSION = 1
"""The contract number emitted as the first `--porcelain` line. Documented in
`docs/prompt.md`: keys are only ever ADDED within a version, never renamed or removed,
so a script that greps one key keeps working and one that requires a new key can say so."""

_ZSH = {"name": "blue", "count": "cyan", "ahead": "yellow", "warn": "red"}
"""Part -> zsh colour name. Only `colour="zsh"` reads this; anything else is plain."""


def render_prompt(status: Status, *, colour: str = "") -> str:
    """One line, or "" when this project has nothing worth a prompt segment.

    `colour="zsh"` wraps each part in `%F{…}%f`. Any other value is plain text.
    """
    if not status["total"]:
        return ""
    parts = [_ink(f"tk:{status['project']}", "name", colour)]
    open_, mine = _open(status), len(status["mine"])
    if open_ or mine:
        parts.append(_ink(f"{open_}▸{mine}" if mine else str(open_), "count", colour))
    if ahead := status["sync"]["ahead"]:
        parts.append(_ink(f"⇡{ahead}", "ahead", colour))
    if not status["reports"]["yesterday_narrated"]:
        parts.append(_ink("!r", "warn", colour))
    return " ".join(parts) if len(parts) > 1 else ""


def _open(status: Status) -> int:
    return sum(n for name, n in status["counts"].items() if name in OPEN_STATUSES)


def _ink(text: str, part: str, colour: str) -> str:
    return f"%F{{{_ZSH[part]}}}{text}%f" if colour == "zsh" else text


def render_porcelain(status: Status) -> str:
    """`key=value`, one per line, for anything scripting against status.

    Counts and flags only — no title and no free text ever reaches this, so a value can
    never contain a newline or an `=` and a reader may split on the first one forever.
    """
    stuck, reports = status["bottleneck"], status["reports"]
    pairs = [("version", PORCELAIN_VERSION), ("project", status["project"]),
             ("root", status["root"]), ("actor", status["actor"]),
             ("total", status["total"]), ("open", _open(status)),
             ("ready", status["ready"]), ("blocked", status["blocked"]),
             ("mine", len(status["mine"])), ("others", len(status["others"])),
             ("idle", status["idle"]), ("idle_days", status["idle_days"]),
             ("bottleneck", stuck["task"] if stuck else ""),
             ("blocks", stuck["blocks"] if stuck else 0),
             ("remote", status["sync"]["host"]), ("ahead", status["sync"]["ahead"]),
             ("today_events", reports["today_events"]),
             ("yesterday", reports["yesterday"]),
             ("yesterday_written", int(reports["yesterday_written"])),
             ("yesterday_narrated", int(reports["yesterday_narrated"])),
             ("prompt", render_prompt(status))]
    return "\n".join(f"{key}={value}" for key, value in pairs)
