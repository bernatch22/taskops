"""The window is a LEASE, not a file — who serves the dashboard for a checkout.

Four `taskops ui` servers were found alive on one laptop (2026-08-10): one from
four days earlier still running v1's module path, one from a package since
uninstalled, and two from that morning. Each had been orphaned the same way —
`ui.json` records only the LATEST window's port, so the moment a second window
wrote it, the first became unnameable: alive, serving stale code, invisible to
every later `taskops ui`, and killable only by `ps`. A pidfile would be the
obvious patch and the wrong one: a pidfile outlives its process and then lies,
which is the exact failure mode this project already refused once — a stored
`doing` (ARCHITECTURE.md §3). The board's answer applies unchanged: the mutex
must DIE with its holder, and an abandoned holder must expire on its own.

So the same two mechanisms, at the OS layer:

* **`flock` is the mutex, exactly as a lease row's PRIMARY KEY is.** The kernel
  releases it when the process exits — `kill -9` included — so it cannot lie
  about a dead holder the way a pidfile does. One window per checkout becomes a
  fact, not a convention: a second `taskops ui` either holds the lock or talks
  to the process that does. Clobbering `ui.json` into an orphan is structurally
  impossible, because the loser never gets far enough to write it.

* **Idle retirement is the lease expiring.** Every zombie found had served
  NOBODY for days. `watcher.py` already states the lifetime rule — started when
  somebody is listening, gone once nobody is — and this applies it to the whole
  process: no feed subscriber (an open tab holds one) and no request for
  `IDLE_SECONDS` → the window shuts itself down, saying so. An orphan is not
  hunted; it stops being.

`ui.json` is demoted to what it always should have been: a CACHE of the
holder's address, trusted only after `/healthz` proves IDENTITY — this
checkout, this version. Before that check, "something answered on the port" was
taken as "our window is up", which is how a fossil binary from four days ago
kept getting its browser tab reopened instead of being noticed.
"""

from __future__ import annotations

import json
import fcntl
import threading
from typing import IO, Any
from pathlib import Path
from urllib.request import urlopen

from .. import _clock
from .._json import as_object
from .._errors import TaskopsError
from .._version import __version__

LOCK = "ui.lock"

IDLE_SECONDS = 30 * 60.0
"""How long a window with no tab and no request keeps serving. Long enough that
lunch does not kill your dashboard (the tab itself holds a feed subscription,
so only CLOSED tabs start this clock); short enough that an orphan dies the
same afternoon instead of surviving four days."""

PATIENCE = (0.3, 0.7, 1.5)
"""Probes for a holder that has the lock but is not answering YET: `claim` is
taken before the socket binds, so a racing second `ui` can arrive in that gap.
Three tries spanning ~2.5s outlives any normal start-up; after that the holder
is wedged and saying so beats waiting forever."""


def claim(folder: Path) -> IO[bytes] | None:
    """The lock, or None because a live process holds it.

    The returned file object IS the lease — hold it for the server's lifetime
    and never close it early. There is deliberately no unlink and no cleanup:
    the file's existence means nothing (only the kernel lock does), so a crash
    leaves nothing behind that can lie."""
    handle = (folder / LOCK).open("ab")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def holder(folder: Path, checkout: Path) -> str:
    """The URL of the window that holds the lock — verified, never assumed.

    Identity beats liveness: an answering port is only OUR window if /healthz
    names THIS checkout and THIS version. Anything else gets the honest
    sentence, because reopening a browser onto a stale or foreign server is the
    bug that motivated this module."""
    state = _cache(folder)
    port, token = int(state.get("port", 0) or 0), str(state.get("token", ""))
    for pause in PATIENCE:
        threading.Event().wait(pause)
        seen = _identity(port) if port else None
        if seen is None:
            state = _cache(folder)  # the holder may have just written its port
            port, token = int(state.get("port", 0) or 0), str(state.get("token", ""))
            continue
        if seen.get("window") != str(checkout):
            continue  # a stale cache naming a port some OTHER process now owns
        if seen.get("version") != __version__:
            raise TaskopsError(
                f"the window for this checkout is already running taskops "
                f"{seen.get('version')} and you are on {__version__} — stop it with "
                f"ctrl-c in its terminal, or wait ~{int(IDLE_SECONDS / 60)} minutes: "
                "a window with no open tab retires itself"
            )
        return f"http://127.0.0.1:{port}/board/ui/?token={token}"
    raise TaskopsError(
        f"something holds {folder / LOCK} but no window answers on port {port or '?'} — "
        "it may be starting (run this again) or wedged: find it with "
        f"`lsof {folder / LOCK}` and stop it there"
    )


def retire_when_idle(
    mounts: Any, httpd: Any, idle: float = IDLE_SECONDS, tick: float = 15.0
) -> threading.Thread:
    """The lease's expiry: no subscriber and no request for `idle` seconds ends
    the window. A daemon thread, so it can never keep the process alive itself."""

    def expire() -> None:
        while True:
            threading.Event().wait(tick)
            quiet = _clock.now() - mounts.last_seen
            if mounts.hub.count("board") == 0 and quiet > idle:
                print(
                    f"no tab open and nothing asked for {int(quiet / 60)} minutes — "
                    "the window retires (taskops ui brings it back)"
                )
                httpd.shutdown()
                return

    thread = threading.Thread(target=expire, daemon=True)
    thread.start()
    return thread


def _cache(folder: Path) -> dict[str, Any]:
    try:
        return as_object(json.loads((folder / "ui.json").read_text()))
    except (OSError, ValueError):
        return {}


def _identity(port: int) -> dict[str, Any] | None:
    """What /healthz says is serving that port, or None for nothing/not-ours.
    A non-taskops process answering is indistinguishable from silence — both
    mean 'this port is not our window'."""
    try:
        with urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1) as answer:  # noqa: S310
            body = as_object(json.loads(answer.read().decode()))
    except (OSError, ValueError):
        return None
    return as_object(body.get("data")) if body.get("ok") else None
