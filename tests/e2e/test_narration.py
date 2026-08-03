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
from taskops.storage import Store, resolve_root
from taskops.transports.http import live
from taskops.transports.http._wire import Reply, Request
from taskops.transports.http.policy import Policy
from taskops.transports.http.router import build
from taskops.usecases import Selector, digest, follow, init, narration, plan, report_path
from taskops.usecases._narrating import FLUSH_CHARS
from taskops.usecases.milestone import open_chapter

LABEL = "2026-01-02"
ELSEWHERE = "/somewhere/else"


def _message(root: str, kind: str = "narration.delta",
             text: str = "el día empezó") -> WireMessage:
    return WireMessage(kind=kind, label=LABEL, text=text, root=root)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    # Every card belongs to a chapter: the fixture opens one so the test can be about its own
    # subject rather than about that.
    init(tmp_path, install_git_hooks=False)
    open_chapter(tmp_path, "the chapter these tests plan into",
                 actor="dev:berna")
    plan(tmp_path, [{"title": "Something happened", "spec": "It did."}], actor="dev:berna")
    # RESOLVED, because that is what `follow` compares a message's `root` against — and on
    # macOS `tmp_path` is a symlink into `/private`, so the unresolved form never matches.
    return resolve_root(tmp_path)


# ---- the feed


def test_a_wire_message_is_yielded_straight_through(project: Path) -> None:
    """It is NOT a cursor signal. An event enqueues "go read the database"; a wire message is
    the payload itself, because nothing wrote it anywhere and nothing ever will."""
    mine = _message(str(project))
    feed = follow(project, tick=0.05)
    assert next(feed) is None, "the first tick should be quiet"
    WIRE.publish(mine)
    assert next(feed) == mine
    feed.close()


def test_watching_a_narration_writes_nothing_to_the_event_log(project: Path) -> None:
    """THE constraint. `events.jsonl` is committed, and a thousand fragments of prose in it
    would destroy the one property it has: that a human can read its diff."""
    mine = _message(str(project))
    with Store(project) as store:
        before = store.events.max_seq()
    feed = follow(project, tick=0.05)
    next(feed)
    for _ in range(20):
        WIRE.publish(mine)
    assert next(feed) == mine
    feed.close()
    with Store(project) as store:
        assert store.events.max_seq() == before


# ---- the isolation between projects


def _second_project(factory: pytest.TempPathFactory) -> Path:
    """Another board on the same server — the neighbour whose screen must stay clean."""
    home = factory.mktemp("other-project")
    init(home, install_git_hooks=False)
    open_chapter(home, "the chapter these tests plan into",
                 actor="dev:berna")
    return home


def test_a_narration_reaches_its_own_board_and_no_other(
        project: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    """THE leak, executable. `WIRE` is process-global, so one `taskops serve` holding two
    boards open used to broadcast every delta of every report to both — and that prose names
    the strategies and the data of the project that wrote it.

    Two stores, two follows, one publish stamped with A's root: A yields it, B never does.
    """
    # A SIBLING, never a subdirectory: `init` under an existing project reuses the enclosing
    # one (projects do not nest), and two follows on the same root would prove nothing.
    other = resolve_root(_second_project(tmp_path_factory))
    mine = _message(str(project))

    a = follow(project, tick=0.05)
    b = follow(other, tick=0.05)
    try:
        assert next(a) is None and next(b) is None    # both parked and subscribed
        WIRE.publish(mine)
        assert next(a) == mine
        # B is not merely late — it drains the very same publish and yields a quiet tick.
        assert next(b) is None
    finally:
        a.close()
        b.close()


def test_a_message_from_another_project_never_reaches_this_feed(project: Path) -> None:
    """The regression, from the other side: a foreign delta arriving fifty times a second
    must not even show up as narration, let alone as prose."""
    feed = follow(project, tick=0.05)
    try:
        assert next(feed) is None
        for _ in range(10):
            WIRE.publish(_message(ELSEWHERE, text="the other project's secret plan"))
        assert next(feed) is None, "a foreign narration was delivered"
    finally:
        feed.close()


def test_a_message_with_no_root_is_dropped(project: Path) -> None:
    """A DECISION, not an oversight: the insecure default is the one that leaks.

    An older publisher (or an older server sharing the process for a moment across a restart)
    can emit a message with no `root`. Delivering it to every board "for compatibility" would
    be exactly the bug this closes, so it is dropped. The cost is a few seconds of missing
    animation during an upgrade; the file on disk is the durable copy either way.
    """
    orphan: Any = {"kind": "narration.delta", "label": LABEL, "text": "from nowhere"}
    feed = follow(project, tick=0.05)
    try:
        assert next(feed) is None
        WIRE.publish(orphan)
        assert next(feed) is None, "a message with no root was broadcast"
    finally:
        feed.close()


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
    monkeypatch.setattr(live, "follow", _feed_of(_message(str(project))))
    frames = live._ws_frames(project)
    next(frames)                                  # hello
    payload = json.loads(_unframed(next(frames)))
    assert payload["type"] == "narration"
    assert payload["message"] == {"kind": "narration.delta", "label": LABEL,
                                  "text": "el día empezó"}
    frames.close()


def test_the_sse_fallback_names_the_event_narration(
        project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`curl -N /api/live` is a working debugging tool by design, and that is how this feature
    was verified by hand — so the fallback has to carry it too."""
    monkeypatch.setattr(live, "follow", _feed_of(_message(str(project))))
    frames = live._frames(project)
    next(frames)                                  # hello
    frame = next(frames).decode("utf-8")
    assert frame.startswith("event: narration\ndata: ")
    assert json.loads(frame.split("data: ", 1)[1])["text"] == "el día empezó"
    frames.close()


@pytest.mark.parametrize("build", [live._ws_frames, live._frames])
def test_the_frame_never_carries_the_path_of_the_project(
        project: Path, monkeypatch: pytest.MonkeyPatch, build: Any) -> None:
    """`root` is a routing field for `follow`, not something a browser may read: it is an
    absolute path on the server's filesystem, and on a multi-project server it also names a
    board the caller may hold no token for. Both envelopes strip it — the bytes are the test."""
    monkeypatch.setattr(live, "follow", _feed_of(_message(str(project))))
    frames = build(project)
    next(frames)                                  # hello
    frame = next(frames)
    frames.close()
    assert b"root" not in frame
    assert str(project).encode("utf-8") not in frame


def test_stripping_the_root_does_not_blank_it_for_the_other_feeds(project: Path) -> None:
    """A copy, not a mutation. The broadcast hands the SAME dict to every subscriber, so a
    frame builder that popped the key in place would erase the origin for the feed next to
    it — and a message with no root is dropped, so the neighbouring board would go silent."""
    mine = _message(str(project))
    live._public(mine)
    assert mine["root"] == str(project)


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
    # Stamped by the publisher, or `follow` would drop it and the failure would never
    # reach the screen it was written for.
    assert heard[-1]["root"] == str(project)


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
