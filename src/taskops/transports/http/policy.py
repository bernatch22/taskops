"""Who may do what over HTTP. Three settings, and each one has a deployment behind it.

The studio binds to loopback by default, so on a laptop none of this is load-bearing. It all is
the moment somebody puts it behind nginx to show a team the board — which is the intended use,
so the controls exist before the first person needs them rather than after.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from ..._clock import now
from ._wire import Reply, Request, error_reply

__all__ = ["Policy"]

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass
class Policy:
    token: str = ""
    """Require `Authorization: Bearer <token>`. Empty means open, which is correct on
    loopback and wrong the moment `--host 0.0.0.0` appears."""

    readonly: bool = False
    """Refuse every write. For a board on a screen in a room: a shared display should not be
    able to close somebody's task, and a viewer should not be able to post as an agent."""

    rate_limit: int = 0
    """Requests per minute per process, 0 for none. Not per client: this is one small server
    and the thing it protects against is a page with a broken retry loop, not an attacker —
    who would be stopped by the token, not by a counter."""

    _hits: deque[float] = field(default_factory=deque[float], repr=False)

    def check(self, request: Request) -> Reply | None:
        """None means allowed. Ordered cheapest-first, and auth before everything.

        Auth first so a wrong token cannot consume the rate budget, which would otherwise let
        an unauthenticated caller lock out an authenticated one.
        """
        if refusal := self._auth(request):
            return refusal
        if self.readonly and request.method in _WRITE_METHODS:
            return error_reply(403, "this studio is read-only — start it without "
                                    "--readonly to comment or change a status", "readonly")
        return self._rate()

    def _auth(self, request: Request) -> Reply | None:
        """The header, or `?token=` — and the query form is not laziness.

        `EventSource` has no API for request headers, at all. So an SSE stream behind a token can
        ONLY be authenticated by the URL, and refusing the query form would mean the live feed is
        the one endpoint a token locks out. It is accepted everywhere rather than only on
        `/api/live`, because a rule that holds for one path is a rule somebody will move.

        The cost is a token in the browser's address bar and history. That is acceptable for a
        loopback tool whose token is minted per run; it would not be for a public service, and a
        deployment that needs more should terminate auth at the proxy.
        """
        if not self.token:
            return None
        expected = f"Bearer {self.token}"
        if request.headers.get("authorization") == expected:
            return None
        if request.param("token") == self.token:
            return None
        return error_reply(401, "a bearer token is required — open the URL the studio "
                                "printed, which carries it", "unauthorized")

    def _rate(self) -> Reply | None:
        """A sliding window over a deque. No dependency, no background sweep.

        Old timestamps are dropped on the way in, so the deque cannot grow past the limit and
        nothing has to clean up after an idle hour.
        """
        if not self.rate_limit:
            return None
        # `_clock.now` and not `time.time`: an invariant test enforces the single clock, and the
        # reason applies here too — a rate-limit test that had to sleep for a minute is a test
        # that gets deleted.
        at = now()
        while self._hits and at - self._hits[0] > 60.0:
            self._hits.popleft()
        if len(self._hits) >= self.rate_limit:
            return error_reply(429, f"more than {self.rate_limit} requests a minute — "
                                    f"slow down", "rate_limited")
        self._hits.append(at)
        return None
