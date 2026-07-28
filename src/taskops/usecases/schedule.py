"""The daily sweep's TRIGGERS: the file a Claude Code scheduled task runs, and the once-a-day
guard the session hook obeys.

The schedule itself is NOT ours and this module never pretends otherwise. Claude Code Desktop
keeps a scheduled task's cadence, folder and model in the app; what lives on disk is only the
prompt, at `~/.claude/scheduled-tasks/<name>/SKILL.md`. So `install` writes that file and then
hands back the ONE sentence somebody has to say to Claude to give it a time. A command that
reported "installed a daily schedule" would be lying about the half it cannot do, and the
person would find out a week later, when the reports they thought were being written are not.

No launchd, no cron, no OS-specific anything: Desktop's own scheduler already looks back seven
days on wake and starts exactly one catch-up, which is the "machine opened at 9am writes
yesterday's report" behaviour a cron entry famously does not have.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TypedDict

from .._clock import now
from .._errors import BadRequest
from ..engine import date_of
from ._project import locate

__all__ = ["NAME", "STAMP", "ScheduleFile", "claude_home", "install_schedule",
           "read_schedule", "sweep_due", "mark_swept"]

NAME = "taskops-sweep"
STAMP = "sweep.stamp"

_BODY = """---
name: {name}
description: Write the taskops daily reports that are still missing for {folder}. Runs the \
sweep, which narrates every ended day that has events and no write-up yet.
---

# The daily sweep

```sh
taskops report sweep --repo {folder}
```

That is the whole task. The sweep is a BARRIER, not a clock: it narrates every ended day that
owes prose and costs nothing when there is none, so running it late, early or twice is safe.

Report back in one line what it printed. If it says every ended day is already written up,
that is the expected answer and not a failure — say so and stop.
"""


class ScheduleFile(TypedDict):
    """What is on disk for a scheduled task, plus what remains for a human to do."""

    name: str
    path: str
    exists: bool
    body: str
    ask: str


def claude_home() -> Path:
    """Where Claude Code keeps its configuration. `$CLAUDE_CONFIG_DIR` wins — people who moved
    it did so on purpose, and writing to `~/.claude` anyway would create a directory the app
    never reads."""
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def install_schedule(start: Path | str, *, name: str = NAME) -> ScheduleFile:
    """Write the prompt file. Refuses when Claude Code is not on this machine.

    Refuses rather than `mkdir -p`: a config directory conjured for an app that is not
    installed is a directory nobody will ever look in, and the command would report success
    for a task that can never run.
    """
    folder = locate(start)
    home = claude_home()
    if not home.is_dir():
        raise BadRequest(f"Claude Code was not found here — there is no {home}. Install "
                         f"Claude Code (or set $CLAUDE_CONFIG_DIR) and run this again")
    path = home / "scheduled-tasks" / name / "SKILL.md"
    body = _BODY.format(name=name, folder=folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return ScheduleFile(name=name, path=str(path), exists=True, body=body,
                        ask=_ask(folder, name))


def read_schedule(start: Path | str, *, name: str = NAME) -> ScheduleFile:
    """What is there, if anything — `status` is a question, so a missing file is an answer."""
    folder = locate(start)
    path = claude_home() / "scheduled-tasks" / name / "SKILL.md"
    body = path.read_text(encoding="utf-8") if path.is_file() else ""
    return ScheduleFile(name=name, path=str(path), exists=bool(body), body=body,
                        ask=_ask(folder, name))


def _ask(folder: Path, name: str) -> str:
    """The sentence to say to Claude. Verbatim, because the schedule is set by asking."""
    return (f'create a daily scheduled task at 00:05 named "{name}" that runs '
            f"/taskops:sweep in {folder}")


def sweep_due(root: Path) -> bool:
    """Has this project been swept today? The stamp is a DATE, so a corrupt or empty file
    reads as "not today" and costs one extra sweep, never a lost one."""
    stamp = root / ".taskops" / STAMP
    try:
        return stamp.read_text(encoding="utf-8").strip() != date_of(now())
    except OSError:
        return True


def mark_swept(root: Path) -> None:
    """Stamp BEFORE the sweep runs, not after: ten sessions resuming at once must cost one
    model call, and a stamp written on completion would let all ten through."""
    (root / ".taskops" / STAMP).write_text(date_of(now()), encoding="utf-8")
