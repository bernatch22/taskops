"""Watching a narration being written: the feed, the frames, the endpoint, the file.

The user's report was "aprieto Generate y no hace nada". Everything here is one half of the
answer to that, and each test names which half:

  the FEED     — a wire message reaches a watcher without ever touching the event log
  the FRAMES   — it arrives on the same socket as the board, under its own envelope
  the ENDPOINT — the POST returns at once, and refuses a second run over the same file
  the FILE     — the prose lands on disk while the model is still writing it

`narrate` is faked everywhere below. The point of these tests is the plumbing around the model,
and a suite that shelled out to `claude` would be neither offline nor free.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable, Iterator

import pytest

from taskops.contracts import WireMessage
from taskops.engine import WIRE
from taskops.storage import Store
from taskops.transports.http import live
from taskops.transports.http._wire import Reply, Request
from taskops.transports.http.policy import Policy
from taskops.transports.http.router import build
from taskops.usecases import Selector, digest, follow, init, narration, plan, report_path
from taskops.usecases._narrating import FLUSH_CHARS

LABEL = "2026-01-02"


def _message(kind: str = "narration.delta", text: str = "el día empezó") -> WireMessage:
    return WireMessage(kind=kind, label=LABEL, text=text)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    init(tmp_path, install_git_hooks=False)
    plan(tmp_path, [{"title": "Something happened", "spec": "It did."}], actor="dev:berna")
    return tmp_path


# ---- the feed


def test_a_wire_message_is_yielded_straight_through(project: Path) -> None:
    """It is NOT a cursor signal. An event enqueues "go read the database"; a wire message is
    the payload itself, because nothing wrote it anywhere and nothing ever will."""
    feed = follow(project, tick=0.05)
    assert next(feed) is None, "the first tick should be quiet"
    WIRE.publish(_message())
    assert next(feed) == _message()
    feed.close()


def test_watching_a_narration_writes_nothing_to_the_event_log(project: Path) -> None:
    """THE constraint. `events.jsonl` is committed, and a thousand fragments of prose in it
    would destroy the one property it has: that a human can read its diff."""
    with Store(project) as store:
        before = store.events.max_seq()
    feed = follow(project, tick=0.05)
    next(feed)
    for _ in range(20):
        WIRE.publish(_message())
    assert next(feed) == _message()
    feed.close()
    with Store(project) as store:
        assert store.events.max_seq() == before


# ---- the frames


def _feed_of(*items: object) -> Callable[..., Iterator[object]]:
    def fake(_root: Path, *_args: object, **_kwargs: object) -> Iterator[object]:
        yield from items
        while True:
            yield None
    return fake


def _unframed(frame: bytes) -> str:
    """The JSON inside an RFC 6455 text frame. Cut at the first brace rather than by a fixed
    header width, which changes with the payload length and would make this test depend on how
    long the prose happens to be."""
    return frame[frame.index(b"{"):].decode("utf-8")


def test_the_websocket_carries_narration_under_its_own_type(
        project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A client that has never heard of narration switches on `type` and drops the frame —
    which is why this shares the board's socket instead of opening a second one."""
    monkeypatch.setattr(live, "follow", _feed_of(_message()))
    frames = live._ws_frames(project)
    next(frames)                                  # hello
    payload = json.loads(_unframed(next(frames)))
    assert payload["type"] == "narration"
    assert payload["message"] == _message()
    frames.close()


def test_the_sse_fallback_names_the_event_narration(
        project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`curl -N /api/live` is a working debugging tool by design, and that is how this feature
    was verified by hand — so the fallback has to carry it too."""
    monkeypatch.setattr(live, "follow", _feed_of(_message()))
    frames = live._frames(project)
    next(frames)                                  # hello
    frame = next(frames).decode("utf-8")
    assert frame.startswith("event: narration\ndata: ")
    assert json.loads(frame.split("data: ", 1)[1])["text"] == "el día empezó"
    frames.close()


# ---- the endpoint


def post(payload: dict[str, Any]) -> Request:
    return Request(method="POST", path="/api/report/digest", query={}, headers={},
                   body=json.dumps(payload).encode())


def body_of(reply: Reply) -> Any:
    return json.loads(reply.body)


@pytest.fixture
def blocked(monkeypatch: pytest.MonkeyPatch) -> Iterator[threading.Event]:
    """A digest that hangs until released — the multi-minute model call, without the model."""
    release = threading.Event()

    def fake(*_args: object, **_kwargs: object) -> Path:
        release.wait(timeout=10)
        return Path("nowhere")

    monkeypatch.setattr(narration, "digest", fake)
    try:
        yield release
    finally:
        # Released AND drained: `_running` is module state, so a thread still holding the label
        # would make the NEXT test's first request a 409 out of nowhere.
        release.set()
        _settle(lambda: not narration.running())


@pytest.mark.usefixtures("blocked")
def test_the_post_answers_at_once_and_the_work_goes_on_behind_it(project: Path) -> None:
    """The bug, inverted. This used to block for minutes behind a mute spinner."""
    route = build(project, Policy())
    reply = route(post({"date": LABEL}))
    assert reply.status == 200
    assert body_of(reply) == {"status": "narrating", "label": LABEL}
    assert LABEL in narration.running()


@pytest.mark.usefixtures("blocked")
def test_a_second_narration_of_the_same_report_is_refused(project: Path) -> None:
    """409, not a queue. Two models rewriting one file is corruption: each holds the dossier
    it read at the start, so whichever finishes last silently erases the other."""
    route = build(project, Policy())
    route(post({"date": LABEL}))
    refused = route(post({"date": LABEL}))
    assert refused.status == 409
    assert body_of(refused)["code"] == "already_narrating"


def test_a_failure_arrives_on_the_wire_rather_than_in_the_response(
        project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verbatim, and on the socket: the request is long gone by the time `claude` says it is
    not logged in, and that sentence is the one thing the reader can act on."""
    def explode(*_args: object, **_kwargs: object) -> Path:
        raise RuntimeError("claude is not logged in")

    monkeypatch.setattr(narration, "digest", explode)
    heard: list[WireMessage] = []
    cancel = WIRE.subscribe(heard.append)
    try:
        narration.start(project, LABEL)
        _settle(lambda: any(m["kind"] == "narration.failed" for m in heard))
    finally:
        cancel()
    assert heard[-1]["text"] == "claude is not logged in"
    assert heard[-1]["label"] == LABEL


def _settle(done: Callable[[], bool], tries: int = 100) -> None:
    for _ in range(tries):
        if done():
            return
        threading.Event().wait(0.05)
    raise AssertionError("the narration thread never got there")


# ---- the file


def test_the_prose_reaches_the_file_pass_by_pass(
        project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A run used to leave `_pendiente_` on disk for a quarter of an hour, which is
    indistinguishable from a report nobody narrated — and a crash made that permanent."""
    seen: list[str] = []
    path = report_path(project, LABEL)

    def fake(_dossier: str, *, on_pass: Any = None, on_text: Any = None,
             **_kwargs: object) -> str:
        on_pass(1, 2)
        on_text("the first reading. " * 40)
        on_pass(2, 2)                             # a boundary flushes what came before it
        seen.append(path.read_text(encoding="utf-8"))
        on_text("the second reading.")
        return "the stitched reading."

    monkeypatch.setattr("taskops.usecases.dossier.narrate", fake)
    digest(project, Selector(date=LABEL))
    mid = seen[0]
    assert "the first reading." in mid, "the file was still pending when pass 2 began"
    assert "_pendiente" not in mid
    # And the FINAL file is what `narrate` returned, not the fragments somebody watched:
    # a multi-pass narration returns the stitched reading, and that is the document.
    assert "the stitched reading." in path.read_text(encoding="utf-8")


def test_a_long_single_pass_grows_the_file_before_it_ends(
        project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The common case — one day, one reading. Waiting for a pass boundary that never comes is
    how the first fix would have looked like it worked and changed nothing on screen."""
    path = report_path(project, LABEL)
    grew: list[bool] = []

    def fake(_dossier: str, *, on_pass: Any = None, on_text: Any = None,
             **_kwargs: object) -> str:
        on_pass(1, 1)
        for _ in range(4):
            on_text("x" * FLUSH_CHARS)
            grew.append("xxxx" in path.read_text(encoding="utf-8"))
        return "done"

    monkeypatch.setattr("taskops.usecases.dossier.narrate", fake)
    digest(project, Selector(date=LABEL))
    assert grew[-1] is True, "nothing reached the file until the very end"
