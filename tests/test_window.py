"""cli/window.py — the window is a LEASE, and these pin each half of that.

The zombie population this replaces: four `taskops ui` servers alive at once,
one of them four days old on a module path that no longer existed. Every test
here is one of the ways that happened.
"""

from __future__ import annotations

import json
import threading
from typing import Any, Iterator
from pathlib import Path

import pytest

from taskops import _clock
from taskops.cli import window
from taskops._errors import TaskopsError
from taskops.http.server import BoardServer, serve

pytestmark = pytest.mark.usefixtures("clock")


# ── the mutex ───────────────────────────────────────────────────────────────


def test_one_window_per_checkout_is_a_fact_not_a_convention(tmp_path: Path) -> None:
    """flock: the second claim fails while the first is HELD, and succeeds the
    moment it is released — no pidfile, no cleanup step, nothing that can lie."""
    first = window.claim(tmp_path)
    assert first is not None
    assert window.claim(tmp_path) is None  # a live holder: the loser starts nothing
    first.close()  # what ANY death does — the kernel releases, even on -9
    second = window.claim(tmp_path)
    assert second is not None
    second.close()


def test_a_crash_leaves_nothing_that_lies(tmp_path: Path) -> None:
    """The lock FILE persists after release, and that must mean nothing: only
    the kernel lock is the lease. A pidfile design fails exactly this test."""
    handle = window.claim(tmp_path)
    assert handle is not None
    handle.close()
    assert (tmp_path / window.LOCK).exists()  # the corpse is there…
    fresh = window.claim(tmp_path)
    assert fresh is not None  # …and it grants nothing
    fresh.close()


# ── identity: reuse is verified, never assumed ──────────────────────────────


@pytest.fixture()
def own_window(tmp_path: Path) -> Iterator[tuple[BoardServer, Path, int]]:
    """A real window server for a real checkout, port from the OS."""
    checkout = tmp_path / "checkout"
    (checkout / ".taskops").mkdir(parents=True)
    httpd = serve(checkout / ".taskops", "127.0.0.1", 0, repo=checkout)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd, checkout, httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def test_holder_returns_the_live_windows_url(
    own_window: tuple[BoardServer, Path, int],
) -> None:
    _, checkout, port = own_window
    folder = checkout / ".taskops"
    (folder / "ui.json").write_text(json.dumps({"port": port, "token": "tok"}))
    url = window.holder(folder, checkout)
    # The ROOT, since 2026-08-10. This assertion used to read `/board/ui/`, and
    # that was the CONTRACT changing, not a test bent to fit: `board` is only
    # the name a window mounts its single board under and `/ui/` was a door on a
    # host that serves no page, so neither had any business in the one URL a
    # human types. The board's own routes still hang off `/board`, which is what
    # `test_the_boards_own_routes_still_answer_under_board` next door pins.
    assert url == f"http://127.0.0.1:{port}/?token=tok"


def _get(port: int, path: str) -> bytes:
    """A real request against a real window — the bundle under test is the
    PACKAGED one (`mounts.ui`), not a fake, so this fails if the wheel ever
    stops shipping a page."""
    from urllib.error import HTTPError
    from urllib.request import urlopen

    try:
        with urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as answer:  # noqa: S310
            return bytes(answer.read())
    except HTTPError as err:
        return bytes(err.read())


def test_the_window_serves_its_page_at_the_root(
    own_window: tuple[BoardServer, Path, int],
) -> None:
    """`taskops ui` hands out `http://127.0.0.1:<port>/` and that has to BE the
    page — the old address leaked two implementation details into the one URL a
    human types."""
    _, _, port = own_window
    assert b"<!doctype html>" in _get(port, "/").lower()
    assert b"taskops" in _get(port, "/").lower()
    assert _get(port, "/app.js").startswith(b"(()") or b"function" in _get(port, "/app.js")


def test_the_root_page_does_not_swallow_a_mistyped_path(
    own_window: tuple[BoardServer, Path, int],
) -> None:
    """Deliberately NOT `static.resolve`, whose single-page fallback answers ANY
    tail with the index: at the root that would turn every mistyped API path
    into a page, and the API's honest 404 is worth more than a nicety."""
    _, _, port = own_window
    assert b"nothing at /nope" in _get(port, "/nope")


def test_a_board_host_never_serves_a_page_at_its_root(tmp_path: Path) -> None:
    """`repo is None` is the one switch — the same one /git and /healthz's
    identity read — so a host cannot start serving a dashboard by any route."""
    root = tmp_path / "boards"
    root.mkdir()
    httpd = serve(root, "127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        assert b"nothing at /" in _get(httpd.server_address[1], "/")
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_a_port_owned_by_another_checkouts_window_is_not_ours(
    own_window: tuple[BoardServer, Path, int], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stale-cache case: ui.json names a port that some OTHER checkout's
    window now owns. Liveness says yes; identity says no; the sentence names
    the lock. Before identity existed, this reopened a tab onto the wrong
    board's dashboard."""
    _, _, port = own_window
    foreign = tmp_path / "elsewhere"
    (foreign / ".taskops").mkdir(parents=True)
    (foreign / ".taskops" / "ui.json").write_text(json.dumps({"port": port, "token": "t"}))
    monkeypatch.setattr(window, "PATIENCE", (0.01, 0.01))
    with pytest.raises(TaskopsError, match="ui.lock"):
        window.holder(foreign / ".taskops", foreign)


def test_a_host_with_no_repo_carries_no_identity_and_is_never_reused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A board HOST (`taskops serve`) answers healthz too — tersely, no window
    key, no path leak. `holder` must read that as 'not our window', not as
    'healthy, reuse it': that mistake is how a fossil kept getting its browser
    tab reopened."""
    httpd = serve(tmp_path / "boards", "127.0.0.1", 0)  # no repo: a HOST
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        checkout = tmp_path / "checkout"
        (checkout / ".taskops").mkdir(parents=True)
        (checkout / ".taskops" / "ui.json").write_text(
            json.dumps({"port": httpd.server_address[1], "token": "t"})
        )
        monkeypatch.setattr(window, "PATIENCE", (0.01, 0.01))
        with pytest.raises(TaskopsError, match="ui.lock"):
            window.holder(checkout / ".taskops", checkout)
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_a_window_from_another_version_is_named_not_reused(
    own_window: tuple[BoardServer, Path, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The four-day-old zombie ran code that no longer existed on disk, and
    reuse-by-liveness kept opening tabs onto it. A version mismatch is a
    refusal that names both versions and both ways out — never a silent reuse,
    never a silent replacement."""
    _, checkout, port = own_window
    folder = checkout / ".taskops"
    (folder / "ui.json").write_text(json.dumps({"port": port, "token": "tok"}))
    monkeypatch.setattr(window, "__version__", "9.9.9")
    with pytest.raises(TaskopsError, match="9.9.9") as caught:
        window.holder(folder, checkout)
    assert "ctrl-c" in str(caught.value) and "retires itself" in str(caught.value)


# ── the expiry ──────────────────────────────────────────────────────────────


class _FakeHub:
    def __init__(self, subscribers: int) -> None:
        self.subscribers = subscribers

    def count(self, board: str) -> int:
        return self.subscribers


class _FakeMounts:
    def __init__(self, subscribers: int) -> None:
        self.hub = _FakeHub(subscribers)
        self.last_seen = _clock.now()


class _FakeServer:
    def __init__(self) -> None:
        self.stopped = threading.Event()

    def shutdown(self) -> None:
        self.stopped.set()


def test_a_window_nobody_looks_at_retires_itself(clock: Any) -> None:
    """No subscriber + idle past the threshold → shutdown. This is the clause
    that makes an orphan STOP EXISTING instead of serving nobody for days."""
    mounts, httpd = _FakeMounts(subscribers=0), _FakeServer()
    clock(window.IDLE_SECONDS + 60)  # the silence happened before the check
    window.retire_when_idle(mounts, httpd, tick=0.01)
    assert httpd.stopped.wait(2.0), "the idle window never retired"


def test_an_open_tab_keeps_the_window_alive(clock: Any) -> None:
    """A tab holds a feed subscription; while one exists the window must serve,
    however long the request silence — a dashboard left open over lunch is not
    an orphan."""
    mounts, httpd = _FakeMounts(subscribers=1), _FakeServer()
    clock(window.IDLE_SECONDS * 3)
    thread = window.retire_when_idle(mounts, httpd, tick=0.01)
    assert not httpd.stopped.wait(0.3), "retired with a tab still open"
    httpd.shutdown()  # let the daemon exit NOW, not after the clock unfreezes
    thread.join(1.0)


def test_a_recent_request_keeps_the_window_alive() -> None:
    """Subscribers zero but somebody just asked something (an agent's curl, a
    probe): fresh activity resets the clock."""
    mounts, httpd = _FakeMounts(subscribers=0), _FakeServer()
    thread = window.retire_when_idle(mounts, httpd, tick=0.01)
    assert not httpd.stopped.wait(0.3), "retired despite recent activity"
    httpd.shutdown()
    thread.join(1.0)
