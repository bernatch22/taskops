"""The boards a server process holds open, by name.

A board name is validated against a strict pattern BEFORE it is joined to
a path — v1 validated afterwards, and a name with a slash in it created a
directory outside the root.
"""

from __future__ import annotations

import re
from time import sleep
from pathlib import Path
from threading import Lock, Thread

from . import feed
from .._errors import BadRequest, TaskopsError
from ..store.creds import Credentials
from ..store.stores import Stores

NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")

_PACKAGED_UI = Path(__file__).resolve().parent.parent / "ui"

WATCH_SECONDS = 1.0
"""How often a watched board is asked whether it moved. `head()` is one
`SELECT MAX(seq)` against a rowid — O(1) — so this is cheap enough to run while
anybody is looking, and it runs for nobody otherwise."""


class Mounts:
    """The boards this process serves, opened once and kept."""

    def __init__(self, root: Path, ui: Path | None = None) -> None:
        self.root = root
        # The bundle ships INSIDE the package (src/taskops/ui), so a server
        # needs no --ui flag to have a dashboard: an override is for developing
        # the page, a root-local ui/ is a board host's custom skin, and the
        # packaged one is what everybody actually gets.
        self.ui = ui or (root / "ui" if (root / "ui").is_dir() else _PACKAGED_UI)
        self.credentials = Credentials(root / "live.sqlite")
        self.hub = feed.Hub()
        self._lock = Lock()
        self._boards: dict[str, Stores] = {}
        self._watched: set[str] = set()

    def watch(self, name: str) -> None:
        """Publish when the board moves, whoever moved it.

        The RPC handler publishes its own writes the instant they are durable,
        which covers a board everybody reaches over HTTP. It does NOT cover the
        normal LOCAL setup: there, each agent's MCP server writes through a
        `LocalBoard` straight to the same files, in its own process, and this
        one is never told. The socket connected, said "live", and stayed silent
        for the rest of the session — which is how a live board came to need a
        manual reload.

        So the truth is polled from where the truth actually is: the board's own
        sequence. One thread per watched board, started when somebody is
        listening and gone once nobody is. A duplicated signal costs nothing —
        a message is a poke, and the page refetches.
        """
        with self._lock:
            if name in self._watched:
                return
            self._watched.add(name)
        Thread(target=self._pump, args=(name,), daemon=True).start()

    def _pump(self, name: str) -> None:
        try:
            seen = self.stores(name).head()
            while True:
                # Sleep BEFORE asking whether anybody is listening: `watch` is
                # called on the way into `attach`, which is what subscribes, so
                # checking first would race it and the watcher would exit having
                # watched nothing.
                sleep(WATCH_SECONDS)
                if not self.hub.count(name):
                    return
                head = self.stores(name).head()
                if head != seen:
                    seen = head
                    self.hub.publish(name, {"type": "change", "verb": "", "seq": head})
        except (TaskopsError, OSError):
            return  # a board that went away is not worth a traceback per second
        finally:
            with self._lock:
                self._watched.discard(name)

    def stores(self, name: str) -> Stores:
        if not NAME.match(name):
            raise BadRequest(f"board {name!r} — names are [a-z0-9-], up to 40 characters")
        with self._lock:
            if name not in self._boards:
                self._boards[name] = Stores(self.root / name)
            return self._boards[name]

    def count(self) -> int:
        with self._lock:
            return len(self._boards)

    def close(self) -> None:
        for board in self._boards.values():
            board.close()
        self.credentials.close()
