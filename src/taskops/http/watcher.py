"""One thread per WATCHED board: poll its head, poke the hub when it moves.

Split off `mounts.py` at the 200-line budget, and the seam is what the code is
ABOUT: `Mounts` is the boards this process holds open; this is the loop that
notices one of them moved. Nothing else imports it — `Mounts.watch` is still
the only door, so the lifetime rule (started when somebody is listening, gone
once nobody is) is still stated in one place.

**Why poll at all.** The RPC handler publishes its own writes the instant they
are durable, which covers a board everybody reaches over HTTP. It does NOT
cover the normal LOCAL setup: there, each agent's MCP server writes through a
`LocalBoard` straight to the same files, in its own process, and this one is
never told. The socket connected, said "live", and stayed silent for the rest
of the session — which is how a live board came to need a manual reload. So the
truth is polled from where the truth actually is: the board's own sequence. A
duplicated signal costs nothing — a message is a poke, and the page refetches.
"""

from __future__ import annotations

from time import sleep
from typing import TYPE_CHECKING
from threading import Thread

from .._errors import TaskopsError

if TYPE_CHECKING:  # a NAME for the annotation: `mounts` imports THIS module
    from .mounts import Mounts

WATCH_SECONDS = 1.0
"""How often a watched LOCAL board is asked whether it moved. `head()` is one
`SELECT MAX(seq)` against a rowid — O(1) — so this is cheap enough to run while
anybody is looking, and it runs for nobody otherwise."""

REMOTE_WATCH_SECONDS = 3.0
"""The same question asked of a REMOTE board, and slower on purpose: that `head()` is a
`board` call over the network, not a rowid lookup, so once a second would be a request per
second per open tab against somebody else's server. Three seconds is under the time it takes a
reader to look away and back, and the cost of being late is exactly one tick — the message is a
SIGNAL and the page refetches (`feed.py`). It still runs only while somebody is connected."""


def start(mounts: Mounts, name: str) -> None:
    """Watch `name`, once. A second listener joins the thread already running."""
    if not mounts.claim_watch(name):
        return
    Thread(target=_pump, args=(mounts, name), daemon=True).start()


def _pump(mounts: Mounts, name: str) -> None:
    try:
        seen = _head(mounts, name)
        while True:
            # Sleep BEFORE asking whether anybody is listening: `watch` is
            # called on the way into `attach`, which is what subscribes, so
            # checking first would race it and the watcher would exit having
            # watched nothing.
            sleep(WATCH_SECONDS if mounts.upstream is None else REMOTE_WATCH_SECONDS)
            if not mounts.hub.count(name):
                return
            head = _head(mounts, name)
            # `head and …`: a remote that could not be asked answers 0, and 0
            # is not news — it is silence. Poking on it would tell the page
            # the board rewound every time the network hiccuped.
            if head and head != seen:
                seen = head
                mounts.hub.publish(name, {"type": "change", "verb": "", "seq": head})
    except (TaskopsError, OSError):
        return  # a board that went away is not worth a traceback per second
    finally:
        mounts.drop_watch(name)


def _head(mounts: Mounts, name: str) -> int:
    """Where the truth is: this process's own file, or the server's counter."""
    return mounts.upstream.head() if mounts.upstream else mounts.stores(name).head()
