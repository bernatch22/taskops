"""The zero-setup trigger: a session starting kicks the daily sweep off DETACHED.

A scheduled task is the good path and needs Claude Code Desktop plus a sentence said to
Claude. This is the one that needs nothing — if you open a session at 9am, yesterday gets
written up. It is the BACKUP, so it is bound by three rules it may never break:

*Never block.* Hooks are synchronous and the session waits on them. So this spawns and
returns: `start_new_session=True` detaches the child from the session's process group (it
outlives the hook, and a Ctrl-C in the terminal does not kill it), and stdio goes to devnull
because a child writing to the hook's stdout would corrupt the JSON the harness parses.

*Never speak.* Every failure is swallowed. A sweep that cannot run is a report nobody gets;
a hook that raises is a session nobody starts, and that is not a trade taskops gets to make.

*Never repeat.* One sweep per project per day, stamped before the spawn — resuming ten
sessions in a morning must not be ten model calls. `TASKOPS_NO_SWEEP=1` turns it off.
"""

from __future__ import annotations

import os
import subprocess  # noqa: S404 - spawning our own CLI, argv list, never a shell
import sys
from pathlib import Path

from ..._errors import TaskopsError
from ...usecases import board, read_remote
from ...usecases.schedule import mark_swept, sweep_due

__all__ = ["launch_sweep", "command_for"]


def command_for(root: Path) -> list[str]:
    """The child's argv. `sys.executable -m` rather than the `taskops` script: the hook may be
    running under a virtualenv whose bin directory is not on the harness's PATH, and the
    interpreter that is executing this line is by definition the one that can import us."""
    return [sys.executable, "-m", "taskops.transports.cli.main",
            "report", "sweep", "--repo", str(root)]


def launch_sweep(cwd: str) -> None:
    """Fire and forget, or silently do nothing. NEVER raises — see the module docstring."""
    try:
        root = _worth_sweeping(cwd)
        if root is None:
            return
        mark_swept(root)
        _spawn(command_for(root))
    except (TaskopsError, OSError, ValueError):
        return


def _worth_sweeping(cwd: str) -> Path | None:
    """The project to sweep, or None for every reason not to.

    A project with no remote AND nothing on the board has nothing to narrate and nowhere to
    send it, so the check is here rather than inside the sweep: the cheap answer must be
    reached without paying for a process, or the guard costs more than the thing it guards.
    The board stands in for "has this project any history" because a task cannot exist
    without the events that created it — and unlike `.taskops/events.jsonl`, which is the
    mirror and stays empty until a sync, it is true from the first `plan`.
    """
    from ...usecases import locate

    if os.environ.get("TASKOPS_NO_SWEEP") == "1":
        return None
    root = locate(cwd)
    if not board(root)["total"] and read_remote(root) is None:
        return None
    return root if sweep_due(root) else None


def _spawn(command: list[str]) -> None:
    with open(os.devnull, "r+b") as void:
        subprocess.Popen(command, stdin=void, stdout=void, stderr=void,  # noqa: S603
                         start_new_session=True, close_fds=True)
