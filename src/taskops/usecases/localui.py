"""The LOCAL board's web interface: where it is listening, and starting one when it is not.

A project with a remote has an address that exists whether or not anybody is looking — the
server is up, and `taskops open` has a URL to hand a browser. A local project has neither until
somebody runs a blocking command in a spare terminal, which is why `taskops open` used to answer
a project with no remote by refusing and naming a *different* command. Two things fix that and
this module is both: a running UI writes down where it is, and anything that wants one can ask
for it without waiting.

**The port is chosen by the OS, not by us.** Fixing it at 2140 meant the second project you
opened collided with the first — and the failure was a bind error inside a detached child, so
the visible symptom was a URL that never answered. `ui --port 0` binds anything free and records
what it got, which also means several projects' boards can be open at once, which is the normal
case for anybody with more than one repository.

`TASKOPS_NO_UI=1` disables the starting half entirely; reading a note somebody else's `taskops
ui` wrote still works, because that is a board that exists and pointing at it costs nothing.

**A stale note is worse than none**, because it points a browser at a port that may now belong
to something else entirely. So liveness is checked twice, and the cheap check is not enough on
its own: a pid that is alive may be a REUSED pid, so the port has to answer as well.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess  # noqa: S404 - spawning our own CLI, argv list, never a shell
import sys
from pathlib import Path

from ..storage import PROJECT_DIR

__all__ = ["UI_FILE", "note_ui", "forget_ui", "running_ui", "start_ui", "local_ui"]

UI_FILE = "ui.json"
"""`.taskops/ui.json` — pid, port, and nothing else. No credential: a LOCAL ui has no token
unless somebody passed one, and if they did, it is theirs to carry. Gitignored like the rest of
the machine-specific files, because a teammate inheriting this repository's idea of which port
their board is on is a browser pointed at whatever else they happen to be running."""


def _path(root: Path) -> Path:
    return root / PROJECT_DIR / UI_FILE


def note_ui(root: Path, port: int) -> None:
    """Record a UI that has just BOUND. Called by `taskops ui` itself, after the bind and
    never before it — a note written on intent would advertise a port nothing answers on."""
    _path(root).write_text(json.dumps({"pid": os.getpid(), "port": port}), encoding="utf-8")


def forget_ui(root: Path) -> None:
    """Remove the note on a clean exit. Best effort: a UI killed with `-9` leaves it behind,
    which is exactly the case `running_ui` verifies rather than trusts."""
    _path(root).unlink(missing_ok=True)


def running_ui(root: Path) -> int:
    """The port a live UI for this project is on, or 0.

    Both checks, and the order is the cheap one first: a dead pid answers in microseconds and
    is the common case for a stale file. The connect is what catches a pid the kernel has since
    handed to something else — it is a loopback TCP handshake, so it costs well under a
    millisecond and never leaves the machine.
    """
    try:
        noted = json.loads(_path(root).read_text(encoding="utf-8"))
        pid, port = int(noted["pid"]), int(noted["port"])
    except (OSError, ValueError, KeyError, TypeError):
        return 0
    try:
        os.kill(pid, 0)                      # signal 0: "does this process exist", no delivery
    except (OSError, ProcessLookupError):
        return 0
    with socket.socket() as probe:
        probe.settimeout(0.25)
        return port if probe.connect_ex(("127.0.0.1", port)) == 0 else 0


def start_ui(root: Path) -> int:
    """Start a UI for this project DETACHED and return its port, or 0 if it did not come up.

    Detached the same way the daily sweep is, and for the same reason: the caller is a hook or
    a command somebody is waiting on, and a web server that ran in the foreground would be a
    session that never starts. `start_new_session` cuts it out of the caller's process group,
    so it survives the hook and a Ctrl-C in that terminal does not take the board down with it.

    Returns 0 rather than raising on every failure. Nobody asked for a board to be started —
    it is an offer, and an offer that fails must not become the reason a session cannot open.

    `TASKOPS_NO_UI=1` turns it off, the way `TASKOPS_NO_SWEEP=1` turns off the daily report.
    Both exist for the same person: somebody who does not want a hook starting processes on
    their machine, and who should not have to uninstall the hook to say so. It is also what
    keeps the test suite from binding ports — the one flag every offer like this needs.
    """
    if os.environ.get("TASKOPS_NO_UI") == "1":
        return 0
    try:
        with open(os.devnull, "wb") as quiet:
            subprocess.Popen(  # noqa: S603 - our own console script, argv list, no shell
                [sys.executable, "-m", "taskops.transports.cli.main", "ui",
                 "--repo", str(root), "--port", "0"],
                stdout=quiet, stderr=quiet, stdin=subprocess.DEVNULL, start_new_session=True)
    except (OSError, ValueError):
        return 0
    return _await(root)


def _await(root: Path) -> int:
    """Wait for the child to write its note, briefly. Polled and not slept-through: the common
    case is well under a second, and this runs inside a hook that must not be felt."""
    import time

    for _ in range(40):                       # 40 × 50 ms — an interpreter start, with slack
        if port := running_ui(root):
            return port
        time.sleep(0.05)
    return 0


def local_ui(root: Path, *, start: bool = True) -> str:
    """`http://127.0.0.1:<port>/` for this project's board, or "".

    The one entry point callers want: it does not matter to `taskops open` or to a session
    greeting whether the board was already up, and making them ask twice is how one of them
    ends up handling only half the cases.
    """
    port = running_ui(root) or (start_ui(root) if start else 0)
    return f"http://127.0.0.1:{port}/" if port else ""
