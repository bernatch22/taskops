"""The HTTP surface: routing, the policy, and the endpoints.

Every route is a pure function `Request -> Reply`, so all of this runs with no port open and no
thread — which is the whole reason `_wire` exists. The one test that DOES bind a socket is the
live-feed one, because a generator that never gets pulled proves nothing about a stream.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from taskops.transports.http._wire import Reply, Request
from taskops.transports.http.policy import Policy
from taskops.transports.http.router import build
from taskops.usecases import init, next_task, plan


def get(path: str, **query: str) -> Request:
    return Request(method="GET", path=path, query=dict(query), headers={})


def post(path: str, payload: dict[str, Any], **headers: str) -> Request:
    return Request(method="POST", path=path, query={}, headers=headers,
                   body=json.dumps(payload).encode())


def body_of(reply: Reply) -> Any:
    return json.loads(reply.body)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    init(tmp_path, install_git_hooks=False)
    plan(tmp_path, [{"title": "Write the router", "spec": "A table.", "files": ["r.py"]},
                    {"title": "Then the UI", "spec": "React.", "after": [0]}],
         actor="dev:berna")
    return tmp_path


@pytest.fixture
def route(project: Path) -> Any:
    return build(project, Policy())


# ---- routing


def test_the_board_serialises_to_the_shape_the_ui_expects(route: Any) -> None:
    """The contracts ARE the wire format, so this is the check that they still are.

    `ui/src/contracts.ts` mirrors these names by hand. A rename on the Python side that is
    not mirrored shows up in the UI as `undefined`, and this is where it should fail instead.
    """
    payload = body_of(route(get("/api/board")))
    assert set(payload) == {"repo", "columns", "ready", "total"}
    card = next(c for column in payload["columns"] for c in column["cards"])
    assert set(card) == {"task", "lease", "blocked_by", "blocks", "commits"}
    assert set(card["task"]) >= {"id", "title", "spec", "status", "priority", "files"}


def test_a_task_is_read_by_id(route: Any) -> None:
    board = body_of(route(get("/api/board")))
    task_id = board["columns"][0]["cards"][0]["task"]["id"]
    view = body_of(route(get("/api/task", id=task_id)))
    assert set(view) >= {"task", "lease", "blocked_by", "blocks", "neighbours", "thread"}


def test_a_task_without_an_id_is_a_400(route: Any) -> None:
    reply = route(get("/api/task"))
    assert reply.status == 400
    assert body_of(reply)["code"] == "bad_request"


def test_a_missing_task_carries_the_engines_own_status(route: Any) -> None:
    """The taxonomy already knows `NoSuchTask` is a 404, so a new error type gets the right code
    the day it is added rather than the day somebody remembers to map it."""
    reply = route(get("/api/task", id="tk-nothing"))
    assert reply.status == 404
    assert body_of(reply)["code"] == "no_such_task"


def test_an_unknown_api_path_is_a_404(route: Any) -> None:
    assert route(get("/api/nope")).status == 404


def test_a_wrong_method_is_a_405_not_a_404(route: Any) -> None:
    """The two send a caller to completely different places, and "not found" for a GET on a POST
    route has cost everyone an afternoon at some point."""
    reply = route(Request(method="GET", path="/api/comment", query={}, headers={}))
    assert reply.status == 405
    assert "POST" in body_of(reply)["error"]


def test_an_unknown_non_api_path_serves_the_app(route: Any) -> None:
    """The UI routes in the browser, so a reload on a deep link must serve index.html rather than
    404 — the classic broken-refresh bug in a single-page app."""
    reply = route(get("/task/tk-4f2a9c"))
    assert reply.status == 200
    assert b"<!doctype html" in reply.body.lower() or b"ui not built" in reply.body


# ---- the policy


def test_a_token_is_required_when_one_is_set(project: Path) -> None:
    route = build(project, Policy(token="secret"))
    assert route(get("/api/board")).status == 401
    allowed = Request(method="GET", path="/api/board", query={},
                      headers={"authorization": "Bearer secret"})
    assert route(allowed).status == 200


def test_the_token_is_also_accepted_in_the_query(project: Path) -> None:
    """Not laziness: `EventSource` has NO API for request headers, so an SSE stream behind a token
    can only be authenticated by the URL. Refusing the query form would make the live feed the one
    endpoint a token locks out."""
    route = build(project, Policy(token="secret"))
    assert route(get("/api/board", token="secret")).status == 200
    assert route(get("/api/board", token="wrong")).status == 401


def test_readonly_refuses_writes_and_allows_reads(project: Path) -> None:
    route = build(project, Policy(readonly=True))
    assert route(get("/api/board")).status == 200
    refused = route(post("/api/comment", {"task": "tk-1", "text": "hi"}))
    assert refused.status == 403
    assert body_of(refused)["code"] == "readonly"


def test_readonly_reaches_the_ui_through_config(project: Path) -> None:
    """The UI hides its compose box from this, so it must not have to discover read-only by being
    refused mid-typing."""
    assert body_of(build(project, Policy(readonly=True))(get("/api/config")))["readonly"] is True
    assert body_of(build(project, Policy())(get("/api/config")))["readonly"] is False


def test_the_rate_limit_bites_and_says_so(project: Path) -> None:
    route = build(project, Policy(rate_limit=2))
    assert route(get("/api/board")).status == 200
    assert route(get("/api/board")).status == 200
    limited = route(get("/api/board"))
    assert limited.status == 429
    assert body_of(limited)["code"] == "rate_limited"


def test_a_bad_token_does_not_consume_the_rate_budget(project: Path) -> None:
    """Auth runs BEFORE the counter, so an unauthenticated caller cannot lock out an
    authenticated one — which is what the ordering in `Policy.check` is for."""
    route = build(project, Policy(token="secret", rate_limit=1))
    assert route(get("/api/board")).status == 401
    assert route(get("/api/board", token="secret")).status == 200


# ---- writes


def test_a_comment_reaches_the_thread(route: Any) -> None:
    board = body_of(route(get("/api/board")))
    task_id = board["columns"][0]["cards"][0]["task"]["id"]
    assert route(post("/api/comment", {"task": task_id, "text": "From the UI."})).status == 200
    view = body_of(route(get("/api/task", id=task_id)))
    assert view["thread"][-1]["body"]["text"] == "From the UI."


def test_a_comment_with_mentions_becomes_a_directed_message(route: Any, project: Path) -> None:
    """A human talking to an agent goes through exactly the same path as an agent talking to one,
    so it lands in the same inbox — there is no second mechanism for people."""
    from taskops.usecases import inbox

    board = body_of(route(get("/api/board")))
    task_id = board["columns"][0]["cards"][0]["task"]["id"]
    route(post("/api/comment", {"task": task_id, "text": "Careful with r.py",
                                "mentions": ["agent:ana/one"]}))
    waiting = inbox(project, actor="agent:ana/one")
    assert waiting["messages"][0]["body"]["text"] == "Careful with r.py"


def test_mentions_are_accepted_as_a_comma_separated_string(route: Any, project: Path) -> None:
    """A form field produces one string, a JS array produces a list. A message that silently
    reached nobody is the worst way for this to fail, so both are read."""
    from taskops.usecases import inbox

    board = body_of(route(get("/api/board")))
    task_id = board["columns"][0]["cards"][0]["task"]["id"]
    route(post("/api/comment", {"task": task_id, "text": "hi",
                                "mentions": "agent:ana/one, dev:ana"}))
    assert len(inbox(project, actor="dev:ana")["messages"]) == 1


def test_a_refused_status_change_returns_the_engines_reason(route: Any, project: Path) -> None:
    """The UI shows this string verbatim. A `done` refused for want of a commit explains exactly
    what is missing, and replacing it with "Failed" throws away the only useful part.

    The claimed task is found by STATUS, not by position on the board: this test used to grab the
    first card, which happened to be the blocked one — and when claiming a blocked task by id was
    (correctly) forbidden, the test started exercising a different refusal than the one it names.
    """
    claimed = next_task(project, actor="dev:berna")
    assert claimed["claim"] is not None
    task_id = claimed["claim"]["view"]["task"]["id"]
    reply = route(post("/api/status", {"task": task_id, "status": "done"}))
    assert reply.status == 400
    assert "no commit bound" in body_of(reply)["error"]


def test_a_malformed_body_is_a_400_not_a_traceback(route: Any) -> None:
    """The reader here is a browser we wrote, but also anything a curious person points at the
    port."""
    broken = Request(method="POST", path="/api/comment", query={}, headers={},
                     body=b"{not json")
    assert route(broken).status == 400


def test_the_activity_endpoint_serialises_the_shape_the_view_expects(route: Any) -> None:
    """`ui/src/contracts.ts` mirrors these names by hand, so a rename that is not mirrored shows
    up in the history as `undefined` — this is where it should fail instead."""
    payload = body_of(route(get("/api/activity", since="30d")))
    assert set(payload) == {"repo", "since", "events", "titles", "actors", "kinds", "truncated"}
    assert payload["events"], "a planned project has events"
    # Newest first: a timeline is read from the top, and the log's own order is the opposite.
    stamps = [event["ts"] for event in payload["events"]]
    assert stamps == sorted(stamps, reverse=True)


def test_activity_names_the_tasks_its_events_are_about(route: Any) -> None:
    """The titles ride along with the timeline. Fetching them per row would be a hundred requests
    to render one screen, which is how this view would have become the slow one."""
    payload = body_of(route(get("/api/activity")))
    named = {event["task"] for event in payload["events"]}
    assert named <= set(payload["titles"]) | {""}


def test_an_unreadable_window_is_refused_rather_than_guessed(route: Any) -> None:
    """A window read as 24h when the caller wrote `7days` produces a history that is WRONG and looks
    right."""
    reply = route(get("/api/activity", since="7days"))
    assert reply.status == 400
    assert "not a window" in body_of(reply)["error"]


def test_the_transcript_is_not_on_this_surface(route: Any) -> None:
    """The UI no longer reads conversations, so the route is gone rather than dormant. `taskops
    log` still exists in the terminal, which is where reading a transcript belongs — a browser panel
    that fetched hundreds of kilobytes per card click was paying for something nobody read."""
    assert route(get("/api/log")).status == 404


def test_commits_reach_the_ui_with_their_subject_and_files(route: Any, project: Path) -> None:
    """The board showed bare hashes because `TaskView.commits` was `list[str]` while the event
    underneath carried the subject and the file list all along."""
    from taskops.engine import record
    from taskops.storage import Store

    board_payload = body_of(route(get("/api/board")))
    task_id = board_payload["columns"][0]["cards"][0]["task"]["id"]
    with Store(project) as store:
        record(store, task=task_id, actor="dev:berna", kind="commit",
               body={"sha": "a" * 40, "subject": "feat: the thing",
                     "files": ["src/a.py", "tests/test_a.py"]})

    commits = body_of(route(get("/api/task", id=task_id)))["commits"]
    assert commits[0]["subject"] == "feat: the thing"
    assert commits[0]["files"] == ["src/a.py", "tests/test_a.py"]


# ---- the reports


def test_the_index_lists_every_report_with_today_at_the_top(route: Any, project: Path) -> None:
    """A fresh repository has no files, and the list still has a row: today, `exists: false`.

    A Reports view whose list is empty offers nothing to press, and generating today's report is
    the whole reason somebody opens it.
    """
    payload = body_of(route(get("/api/reports")))
    assert len(payload) == 1
    assert set(payload[0]) == {"label", "path", "exists", "stale", "missing_events",
                               "has_narration", "bytes"}
    assert payload[0]["exists"] is False and payload[0]["bytes"] == 0

    from taskops.usecases import Selector, write_report
    write_report(project, Selector(date="2026-01-02"))
    write_report(project, Selector(date="2026-01-03"))
    labels = [row["label"] for row in body_of(route(get("/api/reports")))]
    assert labels[1:] == ["2026-01-03", "2026-01-02"], "newest first"


def test_a_range_label_is_opaque_and_never_parsed_as_a_day(route: Any, project: Path) -> None:
    """Report ranges land in the same directory named for the range. Anything that read the stem
    as a date would raise on the first weekly report — so staleness is simply not answered for
    one, rather than guessed."""
    directory = project / ".taskops" / "reports"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "2026-01-01..2026-01-07.md").write_text("# a week\n", encoding="utf-8")
    (directory / "all.md").write_text("# everything\n", encoding="utf-8")

    rows = {row["label"]: row for row in body_of(route(get("/api/reports")))}
    assert rows["all"]["stale"] is False and rows["all"]["missing_events"] == 0
    assert rows["2026-01-01..2026-01-07"]["exists"] is True


def test_the_index_says_which_reports_carry_a_narration(route: Any, project: Path) -> None:
    from taskops.render import narrated
    from taskops.usecases import Selector, write_report

    path = write_report(project, Selector(date="2026-01-02"))
    assert body_of(route(get("/api/reports")))[1]["has_narration"] is False
    path.write_text(narrated(path.read_text(encoding="utf-8"), "It was a good day."),
                    encoding="utf-8")
    assert body_of(route(get("/api/reports")))[1]["has_narration"] is True


def test_narrating_is_a_write_and_a_readonly_board_refuses_it(project: Path) -> None:
    """The one endpoint here that costs money: it shells out to `claude`. A board on a screen in
    a room must not be able to spend an API key by being looked at."""
    route = build(project, Policy(readonly=True))
    refused = route(post("/api/report/digest", {"date": "2026-01-02"}))
    assert refused.status == 403
    assert body_of(refused)["code"] == "readonly"


def test_narrating_a_label_that_is_not_a_day_is_refused(route: Any) -> None:
    """`parse_date` is strict, and the refusal names what to pass instead — which is what the UI
    shows verbatim."""
    reply = route(post("/api/report/digest", {"date": "last tuesday"}))
    assert reply.status == 400
    assert body_of(reply)["code"] == "bad_request"


def test_there_is_no_such_route_as_a_get_on_the_digest(route: Any) -> None:
    """405, not 404: the path exists under POST, and 'not found' for that has cost everyone an
    afternoon at some point."""
    assert route(get("/api/report/digest")).status == 405
    unknown = route(get("/api/reports/nope"))
    assert unknown.status == 404 and body_of(unknown)["code"] == "no_such_route"
