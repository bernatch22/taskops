"""The board: one interface, three implementations, routing decided ONCE.

    open_board(path, actor) -> LocalBoard | RemoteBoard | Absent

After that call there is no flag to forget: a `RemoteBoard` write that cannot
reach the server raises `Unreachable` naming the URL — it never falls back to a
local store, which is how v1 got two machines each owning the same card.

*Which* directory the board lives in, and what its config says, is
`_locate.py` — the filesystem question, answered before any of this.
"""

from __future__ import annotations

import json
from typing import Any, Protocol
from pathlib import Path
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

from . import verbs
from ._json import as_object
from ._errors import NotFound, Unreachable, from_code
from ._locate import DIR, ADDRESS, find_root, is_project, read_config
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

    def __init__(self, url: str, token: str, actor: str, timeout: float = TIMEOUT) -> None:
        self.url = url.rstrip("/")
        self.token = token
        self.actor = actor
        # Per-board, not global: a caller that must not be kept waiting says so
        # once, at open(). The delivery hook opens with 2s (MENTIONS.md §9a) —
        # a hook that can hang a turn is worse than no hook.
        self.timeout = timeout

    def call(self, verb: str, args: dict[str, Any]) -> dict[str, Any]:
        who = _who(args, self.actor)
        payload = json.dumps({"verb": verb, "args": args, "actor": who}).encode()
        request = Request(  # noqa: S310 — the scheme comes from the board's own config
            f"{self.url}/rpc",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
                "X-Taskops-Actor": who,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                body: dict[str, Any] = json.loads(response.read().decode())
        except HTTPError as err:
            raise _error(err) from err
        except (URLError, TimeoutError, ValueError) as err:
            raise Unreachable(
                f"{self.url} did not answer ({err}). The board is the server's, so nothing "
                "was written. Check the server, or your .taskops/remote.json credential."
            ) from err
        return _unwrap(body, self.url)

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
    """
    root = find_root(start)
    config = read_config(root)
    url = str(config.get("url", ""))
    token = str(config.get("token", ""))
    if url:
        if not token:
            raise Unreachable(
                f"{root / DIR}/board.json points at {url} but there is no credential in "
                "remote.json — run: taskops join <url with ?token= or ?invite=>"
            )
        return RemoteBoard(url, token, actor, timeout)
    if not is_project(root):
        return Absent(root)
    return LocalBoard(root / DIR / "board", actor)


def _unwrap(body: dict[str, Any], url: str) -> dict[str, Any]:
    """The envelope is always an object: {"ok", "seq", "data"} or {"ok", "error"}.
    v1 let three verbs answer with a bare array, which the decoder turned into
    `{}` with no error anywhere. Here a missing envelope is loud."""
    if not body.get("ok", False):
        error = as_object(body.get("error"))
        raise from_code(str(error.get("code", "error")), str(error.get("message", body)))
    if not isinstance(body.get("data"), dict):
        raise Unreachable(f"{url} answered without a data object — is that a taskops server?")
    result = as_object(body.get("data"))
    result.setdefault("seq", body.get("seq", 0))
    return result


def _error(err: HTTPError) -> Exception:
    """An HTTP error still carries the board's own refusal — keep its message."""
    try:
        error = as_object(as_object(json.loads(err.read().decode())).get("error"))
    except (ValueError, OSError):
        error = {}
    if error.get("message"):
        return from_code(str(error.get("code", "error")), str(error["message"]))
    return Unreachable(f"the board answered HTTP {err.code} ({err.reason})")
