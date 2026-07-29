"""The chat sidebar's half of the round trip: the two endpoints, and the feed it rides out on.

The feed test is the one that matters. The sidebar is only worth building if what you type
reaches the session that is open, and that path is `record` -> the bus -> `follow` -> `/api/live`
— which already existed, so this asserts it rather than adding a second notification beside it.
"""

from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from taskops.transports.http._wire import Reply, Request
from taskops.transports.http.policy import Policy
from taskops.transports.http.router import build
from taskops.usecases import follow, init


def get(path: str, **query: str) -> Request:
    return Request(method="GET", path=path, query=dict(query), headers={})


def post(path: str, payload: dict[str, Any]) -> Request:
    return Request(method="POST", path=path, query={}, headers={},
                   body=json.dumps(payload).encode())


def body_of(reply: Reply) -> Any:
    return json.loads(reply.body)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    init(tmp_path, install_git_hooks=False)
    return tmp_path


@pytest.fixture
def route(project: Path) -> Any:
    return build(project, Policy())


def test_a_message_is_read_back_in_the_order_it_was_said(route: Any) -> None:
    """Oldest first: a chat is read from the bottom, so the newest line must be the last one."""
    assert body_of(route(get("/api/chat"))) == []
    for said in ("first", "second", "third"):
        assert route(post("/api/chat", {"text": said})).status == 200
    thread = body_of(route(get("/api/chat")))
    assert [event["body"]["text"] for event in thread] == ["first", "second", "third"]
    assert {event["kind"] for event in thread} == {"chat"}


def test_the_card_on_screen_rides_along_and_is_optional(route: Any) -> None:
    """Optional is the whole feature: the sidebar opens over Reports too, where there is no card."""
    route(post("/api/chat", {"text": "about this one", "card": "tk-1"}))
    route(post("/api/chat", {"text": "about nothing"}))
    thread = body_of(route(get("/api/chat")))
    assert [event["body"]["card"] for event in thread] == ["tk-1", ""]


def test_an_empty_message_is_a_400(route: Any) -> None:
    reply = route(post("/api/chat", {"text": "   "}))
    assert reply.status == 400
    assert body_of(reply)["code"] == "bad_request"


def test_chat_is_behind_the_same_credential_as_every_other_write(project: Path) -> None:
    route = build(project, Policy(token="secret"))
    assert route(post("/api/chat", {"text": "hi"})).status == 401
    assert route(get("/api/chat")).status == 401


def test_a_readonly_board_may_read_the_thread_and_not_add_to_it(project: Path) -> None:
    route = build(project, Policy(readonly=True))
    assert route(get("/api/chat")).status == 200
    refused = route(post("/api/chat", {"text": "hi"}))
    assert refused.status == 403
    assert body_of(refused)["code"] == "readonly"


def test_a_chat_message_reaches_the_live_feed(project: Path) -> None:
    """What makes this more than a notes field. The channel tails `/api/live`, so if the event
    does not appear here it never reaches the session — and nothing else in the app would say so."""
    build(project, Policy())(post("/api/chat", {"text": "are you there"}))
    seen: list[Any] = []
    with closing(follow(project, after=0, tick=0.01)) as feed:
        for event in feed:
            if event is None:
                break
            seen.append(event)
    assert any(e.get("kind") == "chat" and e["body"]["text"] == "are you there" for e in seen)


def test_chat_never_leaves_the_machine() -> None:
    """The decision, pinned. Removing `chat` from `LOCAL_ONLY_KINDS` publishes every line anyone
    ever typed into this box to the whole team, permanently — so it fails here first."""
    from taskops._types import LOCAL_ONLY_KINDS

    assert "chat" in LOCAL_ONLY_KINDS


def test_a_reply_from_the_session_is_told_apart_from_your_own_line(route: Any) -> None:
    """Both sides come through one door on one machine and resolve to the SAME developer id, so
    the answer arrived looking exactly like the question — not invisible, indistinguishable,
    which reads as nothing having happened. `source` is what the actor cannot say."""
    mine = json.loads(route(post("/api/chat", {"text": "why is tk-2 open?"})).body)
    theirs = json.loads(route(post("/api/chat", {"text": "nobody claimed it",
                                                 "source": "session"})).body)
    assert mine["body"]["source"] == "board"
    assert theirs["body"]["source"] == "session"
    assert mine["actor"] == theirs["actor"], "the actor is the same — that is the whole problem"


def test_an_unknown_source_is_read_as_the_board(route: Any) -> None:
    """It labels a door, not a person, so anything that is not the session is somebody typing.
    A browser could post `session` and mislabel one line of its own conversation; that is the
    whole blast radius, and it is why this may ride in the request while the actor may not."""
    said = json.loads(route(post("/api/chat", {"text": "hi", "source": "wharever"})).body)
    assert said["body"]["source"] == "board"
