"""Talking to a taskops server over HTTP, with the standard library and nothing else.

`pyproject` declares `dependencies = []` and that is a feature, not an oversight: taskops
installs into a repository whose owner did not ask for a dependency tree, and a sync client
is the classic place one gets added for the convenience of two lines. `urllib.request` is
those two lines.

**No retries.** A push that fails is re-run by the person who ran it, and the second run
costs nothing because every write here is idempotent — events are content-hashed, a report
PUT compares fingerprints. An automatic retry would therefore be *safe*, which is exactly
why it is a bad idea: it would hide a network that is failing behind a command that always
seems to work. One attempt, a 30-second timeout, and a sentence saying what did not answer.

That argument only got STRONGER when the agent calls arrived. `claim` and `change` are not
idempotent — a retried claim is a second claim, a retried `done` is a second transition — so a
retry here could turn a slow network into a card claimed twice. The failure is typed
(`Unreachable`) precisely so the caller can decide, and for a claim the only safe decision is
to stop.

**Server errors are relayed verbatim.** The server writes its `error` field for a person;
translating it into "HTTP 409" here would throw away the only text that says what to do.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, cast

from .._errors import TaskopsError, Unreachable
from ._sessionfile import bearer_of, expired
from ._wirereply import cause as _cause
from ._wirereply import decode as _decode
from ._wirereply import failure as _message

__all__ = ["Wire", "TIMEOUT", "PAGE"]

TIMEOUT = 30.0
PAGE = 500
"""The batch size in both directions — the cap the server's contract declares."""


class Wire:
    """One remote, six calls — four for replication, two for the writes an agent makes.
    Holds no state beyond where to reach it and how to prove who it is, so a caller may
    build one per command and throw it away."""

    def __init__(self, url: str, token: str, *, timeout: float = TIMEOUT) -> None:
        self.base = url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def post_events(self, events: list[Any]) -> dict[str, Any]:
        """`{"accepted": n, "max_seq": s}` — `accepted` counts the ones that were NEW there."""
        return self.call("POST", "/api/sync", body={"events": events})

    def get_events(self, after: int, limit: int = PAGE) -> dict[str, Any]:
        """One page from the server's log after a SERVER seq. `more` says to ask again."""
        query = urllib.parse.urlencode({"after": after, "limit": limit})
        return self.call("GET", f"/api/sync?{query}")

    def get_report(self, label: str) -> dict[str, Any]:
        """The stored file and its `stamped_seq`. `status` is 404 when the server has none."""
        query = urllib.parse.urlencode({"label": label})
        return self.call("GET", f"/api/report/file?{query}", allow=(400, 404))

    def list_reports(self) -> list[str]:
        """Every label the server holds — the labels-only read, degrading to nothing.

        The contract froze `GET /api/report/file?label=…` before anyone noticed a client
        cannot ASK for a report whose existence it has no way to learn. A listing was
        proposed on the server's card as a purely additive shape; until it lands, a server
        that answers 400/404 here is not an error — it means "reconcile what you know
        about", which is every label already on this disk.
        """
        answer = self.call("GET", "/api/report/file", allow=(400, 404))
        found: Any = answer.get("labels")
        if not isinstance(found, list):
            return []
        return [str(label) for label in cast("list[Any]", found)]

    def put_report(self, label: str, content: str, *, force: bool = False) -> dict[str, Any]:
        """Store a report. `{"stored": true}`, or the 409 body with both seqs in it.

        The conflict is RETURNED rather than raised because it is not an error at this
        layer: reconciling twenty reports must not stop at the first disagreement, and the
        caller's job is to collect them and tell the person which way each one goes.
        """
        body = {"label": label, "content": content, "force": force}
        return self.call("PUT", "/api/report/file", body=body, allow=(409,))

    def claim(self, body: dict[str, Any]) -> dict[str, Any]:
        """`POST /api/next` — a claim decided in the SERVER's sqlite, not in ours."""
        return self.call("POST", "/api/next", body=body)

    def change(self, body: dict[str, Any]) -> dict[str, Any]:
        """`POST /api/update` — the transition, checked by the server's guards."""
        return self.call("POST", "/api/update", body=body)

    def rpc(self, verb: str, args: dict[str, Any]) -> Any:
        """`POST /api/rpc` — any registered verb, executed in the server's store."""
        return self.call("POST", "/api/rpc", body={"verb": verb, "args": args})

    def call(self, method: str, path: str, *, body: Any = None,
             allow: tuple[int, ...] = ()) -> dict[str, Any]:
        """One request. A status in `allow` comes back as data with `status` set."""
        try:
            with urllib.request.urlopen(self._request(method, path, body),
                                        timeout=self.timeout) as answer:
                return _decode(answer.read())
        except urllib.error.HTTPError as err:
            payload = _decode(err.read())
            if err.code in allow:
                return {**payload, "status": err.code}
            stale = expired(self.base, self.token) if err.code == 401 else None
            raise TaskopsError(stale or _message(payload, self.base + path, err.code)) from err
        except (urllib.error.URLError, OSError) as err:
            raise Unreachable(
                f"could not reach {self.base}: {_cause(err)} — the local board is still "
                f"yours; run this again when the network is back") from err

    def _request(self, method: str, path: str, body: Any) -> urllib.request.Request:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(self.base + path, data=data, method=method)
        if self.token:
            # Empty means "this route takes no credential" — the GitHub exchange is the one
            # call in the system made by somebody who has nothing to prove yet, and sending
            # `Bearer ` there invites a 401 from any proxy that parses the header.
            request.add_header("Authorization", f"Bearer {bearer_of(self.token)}")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        return request
