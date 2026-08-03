"""Narrating a report IN THE BACKGROUND, with the prose on the wire as it is written.

The user's report was "aprieto Generate y no hace nada". Nothing was broken: the POST was a
multi-minute call to a model behind a mute spinner, the file said `_pendiente_` for all of it,
and a browser that gave up on the request took the only feedback there was with it.

So the request stops carrying the work. `start` spawns the digest and returns immediately; what
happens next arrives on the socket the board already holds, as `WireMessage`s — a pass
announcement, the prose in fragments, and one terminal frame either way. The engine already
streamed all of this (`engine.narrate`'s `on_pass`/`on_text`, which the terminal has used since
`report --digest` learned to show itself); the only thing missing was somewhere to send it.

**A delta is never an event.** It goes on `WIRE`, not on `BUS`, and never near the database —
`events.jsonl` is committed and its worth is that a human can read its diff.

One at a time per report. Two models rewriting the same file is guaranteed corruption, so a
second request is refused rather than queued: the first is already streaming to the person who
asked, and a queued duplicate would only overwrite it later.
"""

from __future__ import annotations

import threading
from pathlib import Path

from .._errors import AlreadyNarrating, TaskopsError
from ..contracts import WireMessage
from ..engine import WIRE
from ..storage import resolve_root
from ._range import Selector
from .dossier import digest

__all__ = ["narratable_here", "start", "running"]

_lock = threading.Lock()
_running: set[str] = set()
"""Report labels being narrated right now, in THIS process. Process-wide state, like the
channel it publishes to, and for the same reason: the digest runs inside the studio's own
server, so the only narrations this can collide with are the ones it started itself."""


def start(root: Path | str, label: str, *, force: bool = False, model: str = "") -> str:
    """Begin narrating `label` and return at once. Raises `AlreadyNarrating` on a duplicate.

    The caller gets no prose from this — that is the point. It arrives on the wire.
    """
    # Resolved HERE, on the caller's thread, and carried into every frame the run publishes.
    # The channel is process-global: without the origin stamped on each message, a server
    # holding several boards would show this project's prose on all of them. Resolving before
    # the thread starts also means a bad root is an exception the caller sees, not a traceback
    # in the server's stderr.
    origin = str(resolve_root(root))
    with _lock:
        if label in _running:
            raise AlreadyNarrating(f"{label} is being narrated right now — watch it arrive, "
                                   f"or wait for that one to finish before regenerating")
        _running.add(label)
    worker = threading.Thread(target=_run, args=(root, origin, label, force, model),
                              name=f"narrate-{label}", daemon=True)
    # Daemon: a narration is a paid-for convenience, never a reason a server refuses to exit.
    # The dossier is already on disk, and the next run picks up from the file.
    worker.start()
    return label


def narratable_here() -> str:
    """"" when this machine can narrate, else the reason it cannot — asked BEFORE starting.

    A narration is a subprocess of the `claude` the caller is logged into, so where the request
    is SERVED decides whether it can happen at all. On a laptop it can. On a box running
    `taskops serve` there is usually no `claude` and certainly no session, so the Generate
    button used to start a thread that failed two seconds later on a socket the person may not
    have been watching — and the sentence it failed with was about a missing binary, on a
    machine they never chose to run anything on.
    """
    import shutil

    if shutil.which("claude"):
        return ""
    return ("this board is served from a machine with no `claude` on it, so it cannot narrate — "
            "a narration is a subprocess of the CLI somebody is logged into. Run "
            "`taskops report day --digest` on your own machine: it writes the prose there and "
            "sends it here, which is also whose subscription pays for it.")


def running() -> frozenset[str]:
    """Which reports are being narrated. Read by tests and by anything wanting to say so."""
    with _lock:
        return frozenset(_running)


def _run(root: Path | str, origin: str, label: str, force: bool, model: str) -> None:
    """The digest, with every callback turned into a frame. Never raises: it IS the top of a
    thread, so an escaping exception would print a traceback into the server's stderr and tell
    the person watching nothing at all."""
    try:
        digest(root, Selector(date=label), model=model, force=force,
               on_pass=lambda n, total: _say(origin, "narration.pass", label, f"{n}/{total}"),
               on_text=lambda text: _say(origin, "narration.delta", label, text))
        _deliver(root, origin, label)
        _say(origin, "narration.done", label, "")
    except Exception as err:                     # noqa: BLE001 — the reader is the error's audience
        # Verbatim. `claude` missing or logged out is a thing the person can fix in a minute,
        # and only if the sentence reaches the screen instead of becoming "failed".
        _say(origin, "narration.failed", label, str(err) or err.__class__.__name__)
    finally:
        with _lock:
            _running.discard(label)


def _deliver(root: Path | str, origin: str, label: str) -> None:
    """Send it, if this project has a server. A narration nobody else can read is not one.

    Every path that writes prose now ends here, and they did not: the sweep pushed (once its
    own default was fixed), `report --digest` did not, and the UI's Generate button did not —
    so on a hosted board two of the three wrote to somebody's laptop and stopped. The narration
    is the ONE part of a report nothing can regenerate, so where it lands is not a detail.

    Never fatal. The prose is on disk and `push` is idempotent, so an unreachable server means
    "send it later", not "you lost the paragraph you paid a model to write".
    """
    from .pushpull import push
    from .remote import read_remote

    if read_remote(root) is None:
        return
    try:
        push(root)
    except TaskopsError as gone:
        _say(origin, "narration.pass", label, f"written here; not sent yet — {gone}")


def _say(origin: str, kind: str, label: str, text: str) -> None:
    WIRE.publish(WireMessage(kind=kind, label=label, text=text, root=origin))
