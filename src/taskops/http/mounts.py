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
from .._errors import NotFound, BadRequest, TaskopsError
from .upstream import Upstream, seq_of
from ..store.creds import Credentials
from ..store.stores import Stores

NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")

_PACKAGED_UI = Path(__file__).resolve().parent.parent / "ui"

WATCH_SECONDS = 1.0
"""How often a watched LOCAL board is asked whether it moved. `head()` is one
`SELECT MAX(seq)` against a rowid — O(1) — so this is cheap enough to run while
anybody is looking, and it runs for nobody otherwise."""

REMOTE_WATCH_SECONDS = 3.0
"""The same question asked of a REMOTE board, and slower on purpose: that
`head()` is a `board` call over the network, not a rowid lookup, so once a
second would be a request per second per open tab against somebody else's
server. Three seconds is under the time it takes a reader to look away and back,
and the cost of being late is exactly one tick — the message is a SIGNAL and the
page refetches (`feed.py`). It still runs only while somebody is connected."""


class Mounts:
    """The boards this process serves, opened once and kept.

    `upstream` is the whole local/remote switch, and like `repo` it is decided by
    the CALLER at construction, never sniffed per request. With one, this process
    holds no board of its own: every /rpc is relayed to the server that does
    (`upstream.py`), while /git and /ui stay local — which is the point of the
    window (ARCHITECTURE.md §16).
    """

    def __init__(
        self,
        root: Path,
        ui: Path | None = None,
        repo: Path | None = None,
        upstream: Upstream | None = None,
    ) -> None:
        self.root = root
        self.upstream = upstream
        # The ONE place that decides whether this process can read a repo, and
        # it is decided by the CALLER at construction — never sniffed per
        # request. `taskops ui` sits inside a checkout and hands its root;
        # `taskops serve` sits in a boards directory and hands nothing, so its
        # /git door refuses with a message that says exactly that (gitdoor.py).
        self.repo = repo
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
            seen = self._head(name)
            while True:
                # Sleep BEFORE asking whether anybody is listening: `watch` is
                # called on the way into `attach`, which is what subscribes, so
                # checking first would race it and the watcher would exit having
                # watched nothing.
                sleep(WATCH_SECONDS if self.upstream is None else REMOTE_WATCH_SECONDS)
                if not self.hub.count(name):
                    return
                head = self._head(name)
                # `head or …`: a remote that could not be asked answers 0, and 0
                # is not news — it is silence. Poking on it would tell the page
                # the board rewound every time the network hiccuped.
                if head and head != seen:
                    seen = head
                    self.hub.publish(name, {"type": "change", "verb": "", "seq": head})
        except (TaskopsError, OSError):
            return  # a board that went away is not worth a traceback per second
        finally:
            with self._lock:
                self._watched.discard(name)

    def _head(self, name: str) -> int:
        """Where the truth is: this process's own file, or the server's counter."""
        return self.upstream.head() if self.upstream else self.stores(name).head()

    def forward(self, board: str, verb: str, raw: bytes) -> tuple[int, bytes]:
        """Relay one /rpc body to the remote board and poke the page if it wrote.

        Status and bytes come back untouched — see `upstream.py` for why a
        refusal must arrive in the server's own words. The poke is the same rule
        as the local path's: published only AFTER the remote confirmed, and it
        carries no payload, so a duplicate (the poll is about to see the same
        move) costs a refetch and nothing else."""
        if self.upstream is None:
            raise NotFound("this host serves its own board — there is nothing to forward to")
        status, answer = self.upstream.rpc(raw)
        seq = seq_of(answer)
        if status == 200 and seq:
            self.hub.publish(board, {"type": "change", "verb": verb, "seq": seq})
        return status, answer

    def check(self, name: str) -> None:
        """This name is servable — and a LOCAL board is opened by asking.

        A window onto a remote board opens NOTHING here: the stores belong to the
        server, and building one would be a second, empty board on this disk with
        the same name as the real one."""
        _named(name)
        if self.upstream is None:
            self.stores(name)

    def stores(self, name: str) -> Stores:
        _named(name)
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


def _named(name: str) -> str:
    """The name wall, in one place: `check` and `stores` are two doors onto it
    and a second copy of the message would drift from the first."""
    if not NAME.match(name):
        raise BadRequest(f"board {name!r} — names are [a-z0-9-], up to 40 characters")
    return name
