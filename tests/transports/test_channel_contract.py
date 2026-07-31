"""The CONTRACT the Claude Code channel consumes — asserted from the Python side.

`plugin/channel/` is TypeScript. It reads two things out of this package and nothing else:

    the FEED   `/api/live` frames it switches on, and the event bodies it classifies
    the WRITE  `/api/comment`, in the exact shape its `reply` tool posts

Neither is exercised by the TS tests: those run the filter with literals, deliberately, so
they need no socket. That leaves a gap exactly where a rename would land — `body["to"]`
becoming `body["status"]`, `mentions` becoming `notify`, the websocket envelope losing its
`type` — and the channel would go quiet rather than fail. This file is that gap closed: every
assertion below is a literal that `plugin/channel/events.ts` or `server.ts` depends on.

Nothing here binds a socket. The frames are the generator's own bytes and the endpoints are
`Request -> Reply`, which is the same trade the rest of `tests/transports` makes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterator

import pytest

from taskops._types import EVENT_KINDS, LOCAL_ONLY_KINDS
from taskops.contracts import CommitRef, Event, Lease
from taskops.contracts.acceptance import ACCEPTANCE_KIND
from taskops.storage import Store, resolve_root
from taskops.transports.cli.commands.ui import DEFAULT_PORT
from taskops.transports.http import live
from taskops.transports.http._wire import Reply, Request
from taskops.transports.http.policy import Policy
from taskops.transports.http.router import build
from taskops.usecases import init, next_task, plan, update
from taskops.usecases._freeing import unassign
from taskops.usecases._handoff import hand_over

CHANNEL = Path(__file__).parents[2] / "plugin" / "channel"


# ---- the fixtures, shaped like the rest of tests/transports


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
    plan(tmp_path, [{"title": "Write the channel", "spec": "A bridge.", "files": ["s.ts"]},
                    {"title": "Then the README", "spec": "Prose."}],
         actor="dev:berna")
    return resolve_root(tmp_path)


@pytest.fixture
def route(project: Path) -> Any:
    return build(project, Policy())


@pytest.fixture
def card(route: Any) -> str:
    board = body_of(route(get("/api/board")))
    return next(c for column in board["columns"] for c in column["cards"])["task"]["id"]


def event_of(project: Path, task: str, kind: str) -> Event:
    with Store(project) as store:
        found = store.events.of_task(task, kinds=(kind,))
    assert found, f"no {kind} event was written"
    return found[-1]


def frames_of(project: Path, monkeypatch: pytest.MonkeyPatch, *items: object) -> Iterator[bytes]:
    """The websocket generator, fed a canned feed — the same trick `tests/e2e/test_narration`
    uses, because a real feed would need a thread to prove nothing extra."""
    def fake(_root: Path, *_a: object, **_k: object) -> Iterator[object]:
        yield from items
        while True:
            yield None
    monkeypatch.setattr(live, "follow", fake)
    return live._ws_frames(project)


def payload_of(frame: bytes) -> Any:
    """The JSON inside an RFC 6455 text frame — cut at the first brace, because the header
    width changes with the payload length."""
    return json.loads(frame[frame.index(b"{"):].decode("utf-8"))


# ---- the feed: the envelope the channel switches on


def test_the_socket_opens_with_hello_and_the_channel_ignores_it(
        project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`changeOf` returns null for this frame. If `hello` ever carried an `event`, the channel
    would announce a phantom board change on every reconnect — and it reconnects every five
    minutes by design (`live.MAX_TICKS`)."""
    frames = frames_of(project, monkeypatch)
    assert payload_of(next(frames)) == {"type": "hello"}
    frames.close()


def test_a_board_change_arrives_as_type_change_with_the_whole_event(
        project: Path, monkeypatch: pytest.MonkeyPatch, route: Any, card: str) -> None:
    """The two field names `plugin/channel/events.ts` reads off the envelope, plus every key
    of `Event` it reads off the payload."""
    route(post("/api/comment", {"task": card, "text": "hi"}))
    frames = frames_of(project, monkeypatch, event_of(project, card, "comment"))
    next(frames)                                        # hello
    frame = payload_of(next(frames))
    assert frame["type"] == "change"
    assert set(frame["event"]) >= {"id", "task", "actor", "kind", "body", "ts"}
    frames.close()


def test_narration_shares_the_socket_under_a_type_the_channel_drops(
        project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """One socket carries two things. The channel forwards board changes only — prose being
    written into a report is not something to interrupt a session for."""
    from taskops.contracts import WireMessage

    frames = frames_of(project, monkeypatch,
                       WireMessage(kind="narration.delta", label="2026-01-02",
                                   text="el día", root=str(project)))
    next(frames)                                        # hello
    assert payload_of(next(frames))["type"] == "narration"
    frames.close()


# ---- the bodies: what `classify` switches on


def test_a_comment_with_mentions_is_a_message_carrying_them(
        route: Any, project: Path, card: str) -> None:
    """`classify` calls this a `mention` — the one category that is about a PERSON being
    addressed. The kind is the routing (`update._say`), so a comment nobody was named in
    cannot reach an inbox, and must not reach the session either."""
    route(post("/api/comment", {"task": card, "text": "careful with s.ts",
                                "mentions": ["agent:ana/one"]}))
    event = event_of(project, card, "message")
    assert event["body"]["mentions"] == ["agent:ana/one"]
    assert event["body"]["text"] == "careful with s.ts"


def test_a_comment_without_mentions_stays_a_comment(route: Any, project: Path, card: str) -> None:
    route(post("/api/comment", {"task": card, "text": "just a note"}))
    assert event_of(project, card, "comment")["body"]["text"] == "just a note"


def test_a_status_move_names_both_ends(project: Path) -> None:
    """`body["from"]` and `body["to"]` are what the channel renders and what it filters on:
    only `review`, `blocked` and `done` are loud."""
    claimed = next_task(project, actor="dev:berna")
    assert claimed["claim"] is not None
    task = claimed["claim"]["view"]["task"]["id"]
    update(project, task, actor="dev:berna", status="review", comment="ready to look at")
    body = event_of(project, task, "status")["body"]
    assert body["to"] == "review" and body["from"] == "claimed"


def test_closing_a_card_is_its_own_kind(project: Path) -> None:
    """`done` is not a `status` event — the channel classifies it separately, and reading
    `body["to"]` alone would miss every closure."""
    assert "done" in EVENT_KINDS
    claimed = next_task(project, actor="dev:berna")
    assert claimed["claim"] is not None
    task = claimed["claim"]["view"]["task"]["id"]
    update(project, task, actor="dev:berna", status="done", comment="no code needed",
           no_code=True)
    assert event_of(project, task, "done")["body"]["to"] == "done"


def test_an_assignment_names_who_it_went_to(project: Path, card: str) -> None:
    with Store(project) as store:
        hand_over(store, card, "agent:ana/one", actor="dev:berna")
    assert event_of(project, card, "handoff")["body"]["assigned_to"] == "agent:ana/one"


def test_a_recovery_says_who_dropped_the_card(project: Path, card: str) -> None:
    """`recovered_from` is the whole difference between a card handed back on purpose and a
    worker that died. Only the second is worth interrupting somebody for."""
    with Store(project) as store:
        store.tasks.set_assignee(card, "agent:ana/one", when=0.0)
        unassign(store, card, "agent:ana/one", "dev:berna")
    assert event_of(project, card, "released")["body"]["recovered_from"] == "agent:ana/one"


def test_the_heartbeat_kind_the_channel_refuses_is_a_real_kind() -> None:
    """`events.ts` denies `activity` unconditionally. If the kind were ever renamed, that
    denial would guard a phantom and the session would fill with keystrokes."""
    assert "activity" in EVENT_KINDS and "activity" in LOCAL_ONLY_KINDS


# ---- the write: the shape `reply` posts


def test_the_reply_tool_shape_is_accepted_and_reaches_the_thread(
        route: Any, card: str) -> None:
    """Exactly the JSON `server.ts` builds: `task`, `text`, `mentions` as a list."""
    reply = route(post("/api/comment", {"task": card, "text": "from the session",
                                        "mentions": ["dev:berna"]}))
    assert reply.status == 200
    thread = body_of(route(get("/api/task", id=card)))["thread"]
    assert thread[-1]["body"]["text"] == "from the session"


def test_an_empty_reply_is_refused_rather_than_recorded(route: Any, card: str) -> None:
    """The tool guards this too, but a channel is a machine talking: the server is the side
    that must not store a blank comment on somebody's card."""
    assert route(post("/api/comment", {"task": card, "text": "  "})).status == 400
    assert route(post("/api/comment", {"text": "orphan"})).status == 400


def test_the_board_endpoint_carries_what_the_snapshot_renders(route: Any) -> None:
    """`summarize` reads these names and nothing else. A rename shows up in the session as a
    board of `undefined` cards held by `undefined`."""
    board = body_of(route(get("/api/board")))
    assert {"repo", "ready", "total", "columns"} <= set(board)
    column = board["columns"][0]
    assert {"status", "cards"} <= set(column)
    card = next(c for col in board["columns"] for c in col["cards"])
    assert {"id", "title"} <= set(card["task"]) and "lease" in card


def test_the_task_endpoint_carries_what_a_review_line_says(route: Any, card: str) -> None:
    """`readCard` in `events.ts` reads exactly these names off `/api/task` to route a card that
    landed in `review`: WHO may close it, on what branch, at what commit, over how many
    criteria. A rename here does not break the channel loudly — it makes every review line say
    "No reviewer named" about a card that names one, which is the worst possible failure for a
    routing rule.
    """
    view = body_of(route(get("/api/task", id=card)))
    assert {"task", "lease", "commits", "history"} <= set(view)
    assert "reviewer" in view["task"]
    # The three nested names it reaches for, pinned where they are DECLARED — an unclaimed,
    # uncommitted card has a null lease and no commits, and asserting on the empties would
    # assert nothing.
    assert "branch" in Lease.__annotations__ and "sha" in CommitRef.__annotations__
    assert ACCEPTANCE_KIND == "acceptance" and ACCEPTANCE_KIND in EVENT_KINDS


def test_config_is_the_liveness_probe_and_needs_no_database(project: Path) -> None:
    """`server.ts` decides whether to spawn a UI by asking for this. It must answer on a
    board that is empty, locked, or read-only — anything else and the channel would start a
    second server on a port that is already taken."""
    assert build(project, Policy())(get("/api/config")).status == 200
    assert build(project, Policy(token="secret"))(get("/api/config")).status == 401


# ---- the constants the two sides share by hand


def test_the_channel_defaults_to_the_port_the_ui_defaults_to() -> None:
    """`TASKOPS_UI_PORT` defaults to this number in `server.ts`. They are two files in two
    languages, so the only thing keeping them together is this assertion."""
    assert DEFAULT_PORT == 2140
    assert f"?? {DEFAULT_PORT}" in (CHANNEL / "server.ts").read_text(encoding="utf-8")


def test_the_channel_reaches_only_the_routes_asserted_above() -> None:
    """A cheap inventory: every taskops path the TS names is one this file pins. If somebody
    adds a third endpoint to the channel, this fails until the contract test covers it.

    `sync` joined the list when the channel learned to catch up. It is the board's own
    pagination, and the channel is now one more replica reading by cursor — which is why the
    fix needed no endpoint of its own.
    """
    source = (CHANNEL / "server.ts").read_text(encoding="utf-8")
    used = set(re.findall(r"/api/([a-z]+)", source))
    assert used == {"config", "comment", "chat", "conversation", "board", "live", "task",
                    "sync"}


def test_the_chat_route_answers_the_shape_reply_posts(route: Any) -> None:
    """`reply` with no card posts `{"text": …}` to `/api/chat` — the sidebar is where a message
    naming no card came from, and answering it on whatever card was mentioned last would file a
    conversation under work it is not about. If this route or its one field is renamed, the
    channel would answer into a 404 and the asker would watch nothing arrive."""
    answered = route(post("/api/chat", {"text": "porque nadie la reclamo"}))
    assert answered.status == 200
    assert json.loads(answered.body)["kind"] == "chat"


def test_the_conversation_route_the_channel_opens_on_startup_exists(route: Any) -> None:
    """The channel POSTs it when a session starts, which is what stops a new session opening
    onto the last one's conversation. If the route moved, the channel would fail silently — it
    swallows that error on purpose, because a board that will not cut is a board with a longer
    history, not a broken one."""
    answered = route(post("/api/conversation", {}))
    assert answered.status == 200
    assert json.loads(answered.body)["conversation"]


def test_the_channel_declares_no_permission_relay() -> None:
    """Anybody who can write to the board could otherwise approve tool use in the session.
    The capability is absent BY DECISION, and a decision nobody asserts gets undone."""
    source = (CHANNEL / "server.ts").read_text(encoding="utf-8")
    assert "'claude/channel': {}" in source
    assert "capabilities: { experimental: { 'claude/channel/permission'" not in source
    for line in source.splitlines():
        if "claude/channel/permission" in line:
            assert line.strip().startswith(("//", "*", "/*")), \
                "the relay may only be named in a comment, never declared"


def test_the_channel_catches_up_from_the_cursor_it_already_reads_by() -> None:
    """The gap a live run left, and the shape of its fix.

    A session opened and fifteen seconds later a teammate's worker handed a card over; the
    review was routed to that session and it received NOTHING all run, because the websocket
    was still coming up and a live feed has no memory. So the channel now asks `/api/sync`
    the moment the socket opens — the same cursor pagination every replica uses.

    Pinned here because both halves are easy to get wrong and I got one wrong by hand: the
    first catch-up must be BOUNDED to this process's lifetime (replaying the whole log would
    hand a fresh session other people's finished decisions), and it must go through the same
    filter as a live frame, so an event that arrives twice is delivered once.
    """
    source = (CHANNEL / "server.ts").read_text(encoding="utf-8")
    assert "/api/sync?after=" in source
    assert "STARTED" in source, "the first catch-up is bounded to this session's lifetime"
    assert source.count("forwards(KINDS") == 2, "catch-up and live frames share ONE filter"
