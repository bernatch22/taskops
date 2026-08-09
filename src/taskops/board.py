"""The board: one interface, three implementations, routing decided ONCE.

    open_board(path, actor) -> LocalBoard | RemoteBoard | Absent

After that call there is no flag to forget: a `RemoteBoard` write that cannot
reach the server raises `Unreachable` naming the URL — it never falls back to a
local store, which is how v1 got two machines each owning the same card.

*Which* directory the board lives in, and what its config says, is
`_locate.py` — the filesystem question, answered before any of this.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol
from pathlib import Path

from . import _wire, verbs, _clock, session
from ._errors import Refused, NotFound, Unreachable
from ._locate import DIR, ADDRESS, find_root, is_project, read_config
from .store.creds import EXPIRED
from .store.stores import Stores

__all__ = [
    "Board",
    "LocalBoard",
    "RemoteBoard",
    "Absent",
    "open_board",
    # re-exported so `board` stays the one name a caller has to know
    "DIR",
    "ADDRESS",
    "find_root",
    "is_project",
    "read_config",
]

TIMEOUT = 20.0


class Board(Protocol):
    """What every caller may do. `call` is the only door."""

    url: str

    def call(self, verb: str, args: dict[str, Any]) -> dict[str, Any]: ...

    def close(self) -> None: ...


def _who(args: dict[str, Any], own: str) -> str:
    """`actor=` on the call wins: sub-agents share the session's ONE MCP server,
    so a per-call actor is the only identity a spawned worker has. Remote, the
    server checks it against the credential (a dev may act as its own agents)."""
    return str(args.pop("actor", "") or "") or own


class LocalBoard:
    """A board that lives in this directory. The server runs one of these too —
    `local` is not a degraded mode, it is the same code with no network."""

    def __init__(self, root: Path, actor: str) -> None:
        self.root = root
        self.actor = actor
        self.url = str(root)
        self.stores = Stores(root)

    def call(self, verb: str, args: dict[str, Any]) -> dict[str, Any]:
        return verbs.call(self.stores, verb, _who(args, self.actor), args)

    def close(self) -> None:
        self.stores.close()


class RemoteBoard:
    """A board on a server. Writes never degrade; reads never lie about being fresh."""

    def __init__(
        self,
        url: str,
        token: str,
        actor: str,
        timeout: float = TIMEOUT,
        refresh: Callable[[], str] | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self.token = token
        self.actor = actor
        # Per-board, not global: a caller that must not be kept waiting says so
        # once, at open(). The delivery hook opens with 2s —
        # a hook that can hang a turn is worse than no hook.
        self.timeout = timeout
        # How to get another session when this one runs out, or None when the
        # token is a standing one nobody may replace (`session.py`).
        self.refresh = refresh

    def call(self, verb: str, args: dict[str, Any]) -> dict[str, Any]:
        """One retry, and only for the one case a retry can fix.

        `open_board` refreshes an expired session before the first call, which is
        every CLI invocation. It is NOT every caller: the MCP server opens a board
        once and keeps it for the session, so a process alive longer than the token
        would go from working to refused with a human in no loop at all. The retry
        is narrow on purpose — the server said EXPIRED, this client knows how to
        sign in, so it signs in once and repeats the call. Anything else is raised.

        `_who` is resolved HERE and not in `_post`: it POPS `actor` out of the
        args, so a second attempt would find it gone and silently send the call
        as this board's own identity instead of the sub-agent's.
        """
        who = _who(args, self.actor)
        try:
            return self._post(verb, args, who)
        except Refused as err:
            if self.refresh is None or EXPIRED not in str(err):
                raise
            self.token = self.refresh()
            return self._post(verb, args, who)

    def _post(self, verb: str, args: dict[str, Any], who: str) -> dict[str, Any]:
        body: dict[str, Any] = {"verb": verb, "args": args, "actor": who}
        headers = {"Authorization": f"Bearer {self.token}", "X-Taskops-Actor": who}
        if not self.token:
            # A viewer's window onto a PUBLIC board (`open_board`): no credential
            # to send, and — the part that matters — no ACTOR either. Claiming
            # `dev:berna` while proving nothing is exactly what the server refuses
            # (`http/auth.py::authorize`), so a read-only clone that kept sending
            # its local identity could not read the board it just joined. With
            # neither, the server resolves the caller as `anon`, which is true.
            body.pop("actor")
            headers = {}
        return _wire.post(f"{self.url}/rpc", body, headers, self.timeout)

    def close(self) -> None:
        return None


class Absent:
    """No board here — and opening one is not this code's job.

    `LocalBoard` makes its directories on construction, so handing one back for
    a directory nobody ever ran `init` in turned a READ into a write: the MCP
    server is registered globally, and merely opening a session in an unrelated
    repo left a `.taskops/board/` with six sqlite files in it. Only `init` and
    `join` create a board; everything else refuses and says which one to run.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.url = ""

    def call(self, verb: str, args: dict[str, Any]) -> dict[str, Any]:
        raise NotFound(
            f"there is no taskops board in {self.root} — run `taskops init` here to start "
            "one, or `taskops join <url>` to connect to a shared one. (Nothing was created: "
            "a board is made on purpose, never by opening a session in a directory.)"
        )

    def close(self) -> None:
        return None


def open_board(start: Path, actor: str, timeout: float = TIMEOUT) -> Board:
    """Walk up for `.taskops/`, then decide once: remote if configured, else local.

    A directory that is not a project gets an `Absent` board, never a real one.

    A configured `login` block is where the session comes from: an absent or
    expiring token is minted here, by signing this host's challenge with the key
    named in the config, and nobody is asked for anything (`session.py`). With no
    such block — every board joined before this chapter — the token in the file is
    used exactly as it always was.
    """
    root = find_root(start)
    config = read_config(root)
    url = str(config.get("url", ""))
    if url:
        token = session.fresh(root, config, _clock.now())
        if not token and config.get("readonly"):
            # The VIEWER's window: `taskops join <url>` with no invite against a
            # PUBLIC board. There is no credential because none was ever minted,
            # which is a state and not a failure — reads answer as `anon` and the
            # first write comes back in the SERVER's words, naming how a key gets
            # registered. No `refresh`: there is no session to renew.
            return RemoteBoard(url, "", actor, timeout)
        if not token:
            raise Unreachable(
                f"{root / DIR}/board.json points at {url} but there is no credential in "
                "remote.json — run: taskops join <url with ?token= or ?invite=>"
            )
        return RemoteBoard(url, token, actor, timeout, session.refresher(root, config))
    if not is_project(root):
        return Absent(root)
    return LocalBoard(root / DIR / "board", actor)


