"""A stand-in for the taskops server, speaking exactly the frozen wire contract.

Not the real server: that is a sibling's module, built in parallel, and a client test that
imported it would be testing whether two halves of one codebase agree with each other rather
than whether either agrees with the CONTRACT. This handler is written from the contract text,
so a client that passes here is a client the specified server can serve — which is the only
property worth asserting on this side.

It keeps its state in memory and its rules deliberately simple, EXCEPT for the report rule,
which is copied from the contract in full because the client's whole job around reports is to
react to it correctly: bigger `stamped_seq` wins, equal-but-different is always a 409, and
`force` overwrites and says what it replaced.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Iterator
from urllib.parse import parse_qs, urlparse

TOKEN = "s3cr3t-token"
SESSION = "5e5510n-deadbeef"
GITHUB_TOKEN = "gho_pretend-this-came-from-gh"


class Fake:
    """The server's memory, and the counters a test asserts on."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.seen: set[str] = set()
        self.reports: dict[str, tuple[str, int]] = {}
        self.posts = 0
        self.serve_labels = True
        """False makes `GET /api/report/file` with no label answer 400 — a server from before
        the listing route existed, which the client must degrade past rather than fail on."""

        self.projects = ["axion", "taskops"]
        self.github_ok = True
        """False makes the GitHub exchange answer 403 — the member check saying no."""

        self.session_valid = True
        """False expires the session: every project route answers 401 to `Bearer <session>`
        while the project token keeps working. That asymmetry is the point — the client has
        to tell "log in again" apart from "your token is wrong"."""

        self.seen_github_tokens: list[str] = []

    def authenticate(self, github_token: str) -> tuple[int, dict[str, Any]]:
        """`POST /api/auth/github`, written from the contract text and nothing else."""
        self.seen_github_tokens.append(github_token)
        if not self.github_ok:
            return 403, {"error": "that GitHub account is not on any repo this server serves"}
        return 200, {"login": "jp", "session": SESSION, "projects": list(self.projects)}

    def accept(self, events: list[dict[str, Any]]) -> int:
        new = 0
        for event in events:
            if event["id"] not in self.seen:
                self.seen.add(event["id"])
                self.events.append(event)
                new += 1
        return new

    def page(self, after: int, limit: int) -> dict[str, Any]:
        window = self.events[after:after + limit]
        return {"events": window, "max_seq": after + len(window),
                "more": after + len(window) < len(self.events)}

    def store(self, label: str, content: str, seq: int, force: bool) -> dict[str, Any]:
        held = self.reports.get(label)
        if held is None or force or seq > held[1]:
            self.reports[label] = (content, seq)
            return {"stored": True}
        return {"code": "report_conflict", "ours": held[1], "theirs": seq,
                "error": f"{label} is stamped at seq {held[1]} here and {seq} in your copy"}


def stamped(text: str) -> int:
    """The report's fingerprint, read the way the real server reads it."""
    from taskops.engine import stamped_seq

    return stamped_seq(text)


class Handler(BaseHTTPRequestHandler):
    fake: Fake

    def log_message(self, fmt: str, *args: Any) -> None:
        """Silence. The test's output is the assertion, not an access log."""

    def do_GET(self) -> None:                                    # noqa: N802
        if not self._authorised():
            return
        route = urlparse(self.path)
        query = parse_qs(route.query)
        if route.path == "/api/projects":
            return self._json(200, {"login": "jp",
                                    "projects": [{"name": name, "path": f"/srv/{name}"}
                                                 for name in self.fake.projects]})
        if route.path == "/api/sync":
            after = int(query.get("after", ["0"])[0])
            return self._json(200, self.fake.page(after, int(query.get("limit", ["500"])[0])))
        label = query.get("label", [""])[0]
        if not label:
            if not self.fake.serve_labels:
                return self._json(400, {"error": "label is required"})
            return self._json(200, {"labels": sorted(self.fake.reports)})
        held = self.fake.reports.get(label)
        if held is None:
            return self._json(404, {"error": f"no report {label} here"})
        return self._json(200, {"label": label, "content": held[0], "max_seq": held[1]})

    def do_POST(self) -> None:                                   # noqa: N802
        if urlparse(self.path).path == "/api/auth/github":
            # The one route with no credential: the caller is proving who they are, so
            # demanding a bearer first would be a chicken-and-egg.
            status, answer = self.fake.authenticate(str(self._body().get("github_token", "")))
            return self._json(status, answer)
        if not self._authorised():
            return
        if not urlparse(self.path).path.endswith("/api/sync"):
            # A server from before that route existed. Answering 200 to any POST would make
            # this fake vouch for endpoints the contract never froze — and it silently DID,
            # which let an rpc "read" mistake a sync receipt for a board.
            return self._json(404, {"error": f"no route {self.path}", "code": "no_such_route"})
        body = self._body()
        self.fake.posts += 1
        accepted = self.fake.accept(list(body.get("events", [])))
        self._json(200, {"accepted": accepted, "max_seq": len(self.fake.events)})

    def do_PUT(self) -> None:                                    # noqa: N802
        if not self._authorised():
            return
        body = self._body()
        content = str(body.get("content", ""))
        answer = self.fake.store(str(body.get("label", "")), content, stamped(content),
                                 bool(body.get("force")))
        self._json(200 if answer.get("stored") else 409, answer)

    def _authorised(self) -> bool:
        """The project token, OR a session — the contract says the project routes take both."""
        offered = self.headers.get("Authorization")
        if offered == f"Bearer {TOKEN}":
            return True
        if offered == f"Bearer {SESSION}" and self.fake.session_valid:
            return True
        self._json(401, {"error": "bad or missing token — check `taskops remote`"})
        return False

    def _body(self) -> dict[str, Any]:
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))
        parsed: Any = json.loads(raw or b"{}")
        return parsed if isinstance(parsed, dict) else {}

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def running(fake: Fake) -> Iterator[str]:
    """Serve `fake` on a loopback port until the generator is closed. Yields the base URL."""
    handler = type("Bound", (Handler,), {"fake": fake})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
