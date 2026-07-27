"""A request and a reply, as data. The whole point of this module is testability.

Every route is a pure function `Request -> Reply`, so the routing table, the policy and each
endpoint can be tested by calling them — no socket, no thread, no port. The stdlib handler in
`server` is then the only thing that knows about HTTP at all, and it is the one piece with no
decisions in it.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any, Callable, cast

__all__ = ["Request", "Reply", "Route", "json_reply", "error_reply", "Streamer"]

Streamer = Callable[[], Generator[bytes, None, None]]
"""A reply body produced lazily, for the SSE stream. Called by the server AFTER the headers are
flushed, which is what lets one response stay open for an hour.

`Generator` and not `Iterator`, deliberately: the server must be able to `close()` it. A streamed
body holds a database connection and an event-bus subscription, and leaving those to the garbage
collector is a leak — the traceback of a broken pipe forms a reference cycle, so refcounting does
not reclaim it and the cyclic collector runs whenever it feels like it. That was measured, not
assumed: subscriptions survived seven seconds after the client hung up."""


@dataclass(frozen=True, slots=True)
class Request:
    method: str
    path: str
    query: dict[str, str]
    headers: dict[str, str]
    body: bytes = b""

    def param(self, name: str, default: str = "") -> str:
        return self.query.get(name, default)

    def payload(self) -> dict[str, Any]:
        """The JSON body, or {} — never an exception.

        The caller is a browser we wrote, but also anything a curious person points at the
        port, and a malformed body has to be a 400 from the endpoint's own validation rather
        than a traceback from the parser.
        """
        if not self.body:
            return {}
        try:
            parsed: object = json.loads(self.body)
        except json.JSONDecodeError:
            return {}
        return cast("dict[str, Any]", parsed) if isinstance(parsed, dict) else {}


@dataclass(frozen=True, slots=True)
class Reply:
    status: int = 200
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict[str, str])
    stream: Streamer | None = None
    """Set instead of `body` for a response that never ends. The server checks this first."""


Route = Callable[[Request], Reply]


def json_reply(payload: object, status: int = 200) -> Reply:
    """`default=str` on purpose: a contract is dicts, lists, strings and floats, and anything
    else appearing here is a bug better shown as a string in the UI than a 500 with no clue."""
    return Reply(status=status,
                 body=json.dumps(payload, default=str).encode("utf-8"),
                 headers={"Content-Type": "application/json; charset=utf-8"})


def error_reply(status: int, message: str, code: str = "error") -> Reply:
    """One error shape, everywhere. The UI reads `error` and `code`, so a failure renders as a
    sentence a person can act on rather than a red box with a status number in it."""
    return json_reply({"error": message, "code": code}, status)
