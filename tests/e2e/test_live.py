"""The live feed, against a real socket and a real second process.

Everything else about HTTP is tested as pure functions. This is not, because the claim being made
here is one only a running server can support: **an event written by a DIFFERENT process reaches a
connected browser.** That is the entire reason the feed polls a cursor rather than relying on the
in-process bus — a test that wrote through the same process would pass against an implementation
that only listened to the bus, which is the one that fails in production, where every agent is its
own process.

`http.client.HTTPConnection` rather than `urllib`, deliberately: it gives a `close()` that releases
the socket deterministically. urllib leaves it to the garbage collector, and with
`filterwarnings = ["error"]` a stray ResourceWarning fails an unrelated test.
"""

from __future__ import annotations

import http.client
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Iterator

import pytest

from taskops.transports.http import Policy, bound_port, build_server
from taskops.usecases import init, locate, plan

DEADLINE = 15.0
"""Seconds a test waits for a frame. Generous on purpose: this runs on CI machines that are
sometimes very slow, and a flaky liveness test is one somebody eventually marks skip."""


@pytest.fixture
def project(tmp_path: Path) -> Path:
    init(tmp_path, install_git_hooks=False)
    return tmp_path


class Studio:
    """A real server on an OS-chosen port, plus a client that closes its own socket."""

    def __init__(self, root: Path, policy: Policy) -> None:
        self.server = build_server("127.0.0.1", 0, root, policy)
        self.port = bound_port(self.server)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def open(self, path: str) -> tuple[http.client.HTTPConnection, http.client.HTTPResponse]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=DEADLINE)
        connection.request("GET", path)
        return connection, connection.getresponse()

    def close(self) -> None:
        self.server.shutdown()
        self.server_close()

    def server_close(self) -> None:
        self.server.server_close()


@pytest.fixture
def studio(project: Path) -> Iterator[Studio]:
    running = Studio(locate(project), Policy())
    try:
        yield running
    finally:
        running.close()


def write_from_another_process(root: Path, task_id: str, text: str) -> None:
    """A comment written by a SEPARATE interpreter — the deployment this has to work in.

    `sys.executable -m` rather than the `taskops` entry point, for the same reason the git hooks do
    it: the test may be running from a virtualenv the subprocess's PATH cannot see.
    """
    subprocess.run([sys.executable, "-m", "taskops.transports.cli.main", "update", task_id,
                    "--repo", str(root), "--comment", text, "--actor", "agent:ana/two"],
                   capture_output=True, check=True, timeout=60)


def test_a_write_from_another_process_arrives_on_the_stream(project: Path,
                                                            studio: Studio) -> None:
    """THE test. Everything else about the studio is a rendering detail next to this."""
    task_id = plan(project, [{"title": "Watched", "spec": "x"}])["created"][0]["id"]
    connection, stream = studio.open("/api/live")
    try:
        assert "hello" in _read_until(stream, "hello"), "no frame on connect"
        # The subprocess starts only AFTER the stream is open, or the event would predate the
        # cursor and the test would prove nothing about pushing.
        threading.Thread(target=write_from_another_process,
                         args=(project, task_id, "written by another process"),
                         daemon=True).start()
        assert "written by another process" in _read_until(stream, "written by")
    finally:
        connection.close()


def test_the_stream_sends_a_keepalive_rather_than_going_silent(studio: Studio) -> None:
    """The keepalive is not decoration. It is also the ONLY way this server learns a client went
    away — see `live.KEEPALIVE_TICKS`, which the leak test below is what set."""
    connection, stream = studio.open("/api/live")
    try:
        assert ": keepalive" in _read_until(stream, ": keepalive")
    finally:
        connection.close()


def test_the_stream_requires_the_token_when_one_is_set(project: Path) -> None:
    """And accepts it in the query, because `EventSource` cannot set a header at all."""
    guarded = Studio(locate(project), Policy(token="s3cret"))
    try:
        connection, refused = guarded.open("/api/live")
        assert refused.status == 401
        refused.read()
        connection.close()
        connection, allowed = guarded.open("/api/live?token=s3cret")
        assert allowed.status == 200
        connection.close()
    finally:
        guarded.close()


def test_closing_a_browser_releases_the_feeds_resources(
        project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ten tabs opened and closed. THIS TEST FOUND A REAL LEAK, and rewrote the design.

    The first implementation kept the response open forever and relied on a failed write to notice
    the client had gone. That write does not reliably fail: against a closed loopback socket on
    macOS, writes kept succeeding for over seven seconds, so each closed tab held a bus
    subscription and an open sqlite connection for an unbounded time.

    The fix was to stop fighting it — the stream now ends itself on a schedule (`MAX_TICKS`) and
    `EventSource` reconnects by specification. That makes the bound a design property instead of a
    guess about the operating system, and it is what this test now asserts. The lifetime is patched
    down from five minutes because that is the number production wants.
    """
    from taskops.engine import BUS
    from taskops.transports.http import live

    monkeypatch.setattr(live, "MAX_TICKS", 3)
    studio = Studio(locate(project), Policy())
    try:
        # ZERO is the baseline, not a snapshot. The bus is a module-level singleton shared by the
        # whole session, and an earlier test's stream can still be a moment from release — which is
        # how the first version of this test reported a NEGATIVE leak.
        assert _wait_for_bus(0), "another test's stream is still open — cannot measure from here"
        for _ in range(10):
            connection, stream = studio.open("/api/live")
            _read_until(stream, "hello")
            connection.close()
        assert _wait_for_bus(0), f"{len(BUS)} subscriber(s) leaked"
    finally:
        studio.close()


def _wait_for_bus(target: int) -> bool:
    """Wait for the bus to hold `target` subscribers. True if it got there."""
    from taskops.engine import BUS

    deadline = time.monotonic() + DEADLINE
    while time.monotonic() < deadline:
        if len(BUS) == target:
            return True
        time.sleep(0.2)
    return len(BUS) == target


def _read_until(stream: http.client.HTTPResponse, needle: str) -> str:
    """Read lines until `needle` appears or the deadline passes.

    Line by line rather than `read()`: this response never ends, so a bulk read would block until
    the timeout on every call, including the ones that succeed.
    """
    seen = ""
    deadline = time.monotonic() + DEADLINE
    while time.monotonic() < deadline:
        line = stream.readline()
        if not line:
            break
        seen += line.decode("utf-8", "replace")
        if needle in seen:
            return seen
    return seen
