"""The boards a server process holds open, by name.

A board name is validated against a strict pattern BEFORE it is joined to
a path — v1 validated afterwards, and a name with a slash in it created a
directory outside the root.
"""

from __future__ import annotations

import re
from pathlib import Path
from threading import Lock

from . import feed, watcher
from .. import verbs, _clock
from .login import Host
from .repos import Repos
from ..verbs import project
from .._errors import NotFound, BadRequest
from .upstream import Upstream, seq_of
from ..store.creds import Credentials
from ..store.stores import Stores

NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")

_PACKAGED_UI = Path(__file__).resolve().parent.parent / "ui"

class Mounts:
    """The boards this process serves, opened once and kept.

    `upstream` is the whole local/remote switch, and like `repo` it is decided by
    the CALLER at construction, never sniffed per request. With one, this process
    holds no board of its own: every /rpc is relayed to the server that does
    (`upstream.py`), while /git and /ui stay local — which is the point of the
    window (ARCHITECTURE.md §16).

    `ui` is not a parameter: it is `repo`'s shadow. A window (`taskops ui`) has
    a checkout and serves the bundle; a board host (`taskops serve`) has neither.
    """

    def __init__(
        self,
        root: Path,
        repo: Path | None = None,
        upstream: Upstream | None = None,
    ) -> None:
        self.root = root
        self.upstream = upstream
        # Whether this process can read a repo is decided by the CALLER at
        # construction — a window's own checkout — or, on a serve-mode host,
        # per BOARD from its declared forge's mirror (`repos.py` carries it).
        self.repo = repo
        self.repos = Repos(root, repo, self.stores)
        # ONE switch, not two: the same `repo` that mounts /git mounts the bundle. A
        # dashboard needs the viewer's CLONE to draw a diff, so a process with no clone
        # has no business serving one — see `static.py` for the whole post-mortem. The
        # bundle still ships inside the wheel; what went away is the server-side mount
        # and the `--ui` flag that configured it.
        self.ui = _PACKAGED_UI if repo is not None else None
        self.credentials = Credentials(root / "live.sqlite")
        # The HOST's own identity, and it opens NOTHING until a login asks
        # (`login.py::Host` says why lazily is a rule here, not a taste).
        self.host = Host(root)
        self.hub = feed.Hub()
        # When a request last arrived — the window's idle clock (`cli/window.py`
        # retires a window nobody asks anything of). Written by the handler on
        # every request; a HOST reads it never, and that costs nothing.
        self.last_seen = _clock.now()
        self._lock = Lock()
        self._boards: dict[str, Stores] = {}
        self._watched: set[str] = set()

    def touch(self) -> None:
        """A request happened. Unlocked on purpose: a float assignment is atomic
        in CPython, and the idle clock tolerates a stale read by a tick."""
        self.last_seen = _clock.now()

    def watch(self, name: str) -> None:
        """Poke every listener when this board moves — `watcher.py` owns the how."""
        watcher.start(self, name)

    def claim_watch(self, name: str) -> bool:
        """True to the FIRST caller only: one polling thread per board, ever.
        The set lives here and not in `watcher.py` because it is per-process
        state of THESE mounts — a test that runs two servers must not have them
        share it."""
        with self._lock:
            if name in self._watched:
                return False
            self._watched.add(name)
            return True

    def drop_watch(self, name: str) -> None:
        with self._lock:
            self._watched.discard(name)

    def forward(self, board: str, verb: str, raw: bytes) -> tuple[int, bytes]:
        """Relay one /rpc body to the remote board and poke the page if it wrote.

        Status and bytes come back untouched — see `upstream.py` for why a
        refusal must arrive in the server's own words. The poke is the same rule
        as the local path's: published only AFTER the remote confirmed, and it
        carries no payload, so a duplicate (the poll is about to see the same
        move) costs a refetch and nothing else.

        **Only a WRITE pokes, and forgetting that clause was an infinite loop.**
        Every envelope carries `seq`, so `status == 200 and seq` is true of every
        READ too: a `board` call published "the board changed", the page took the
        frame as news and refetched, that refetch published again — a window on a
        remote board hammered its own server at the coalescing interval, forever,
        with nothing on the board moving. Only the forwarded path had the bug,
        because the local path below asks `writes()` first; asking the same
        registry here is what keeps the two halves from disagreeing again."""
        if self.upstream is None:
            raise NotFound("this host serves its own board — there is nothing to forward to")
        status, answer = self.upstream.rpc(raw)
        seq = seq_of(answer)
        if status == 200 and seq and verbs.writes(verb):
            self.hub.publish(board, {"type": "change", "verb": verb, "seq": seq})
        return status, answer

    def check(self, name: str) -> None:
        """This name is servable — and a LOCAL board is opened by asking.

        A window onto a remote board opens NOTHING here: the stores belong to the
        server, and building one would be a second, empty board on this disk with
        the same name as the real one."""
        named(name)
        if self.upstream is None:
            self.stores(name)

    def stores(self, name: str) -> Stores:
        """OPEN a board. Never create one — that is the whole of this method.

        Until 2026-08-08 this said `Stores(self.root / name)` unconditionally, and
        `Stores` makes its own directory. So a GET for a name nobody had heard of —
        arriving BEFORE any credential was checked, since the router calls `check`
        first and `_credential` second — left a board directory with a cache and a
        lease file on disk: anonymous, unauthorised, permanent, a write caused by a
        stranger's question. Creation is now a server-scope OPERATION
        (`core/scope.py`: `board.create`), via `create()`."""
        named(name)
        with self._lock:
            if name not in self._boards:
                if not (self.root / name).is_dir():
                    raise NotFound(
                        f"no board named {name!r} on this server — a board is created by "
                        "its owner, never by a request for one"
                    )
                self._boards[name] = Stores(self.root / name)
            return self._boards[name]

    def public(self, name: str) -> bool:
        """May a caller with NO credential read this board? GitHub's flag.

        On a host: the board's own recorded fact (`verbs/project.py::is_public`),
        defaulting to private, so every board older than the flag is unchanged.
        On a WINDOW onto somebody else's board there are no stores to ask — an
        `Upstream` with no bearer IS a read-only join, so the window lets its own
        browser in and the REMOTE decides. A window WITH a credential answers
        False and its local door stays exactly as tight as it was.
        """
        if self.upstream is not None:
            return not self.upstream.token
        return project.is_public(self.stores(name))

    def create(self, name: str) -> Stores:
        """The one door that MAY make a board directory, and it is never on the
        anonymous path: callers gate it with `scope.permit("board.create", …)`.
        Creating one that exists is a no-op, so it is safe to run twice."""
        named(name)
        (self.root / name).mkdir(parents=True, exist_ok=True)
        return self.stores(name)

    def forget(self, name: str) -> None:
        """Close a board and drop the handle — `create`'s counterpart. Without
        it a REMOVED board outlives its own directory (`removal.py` says how)."""
        with self._lock:
            stores = self._boards.pop(name, None)
            self._watched.discard(name)
        if stores is not None:
            stores.close()

    def count(self) -> int:
        with self._lock:
            return len(self._boards)

    def close(self) -> None:
        for board in self._boards.values():
            board.close()
        self.credentials.close()
        self.host.close()


def named(name: str) -> str:
    """The name wall, in one place: `check` and `stores` are two doors onto it
    and a second copy of the message would drift from the first."""
    if not NAME.match(name):
        raise BadRequest(f"board {name!r} — names are [a-z0-9-], up to 40 characters")
    return name
