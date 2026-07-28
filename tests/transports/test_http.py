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


def test_the_bundle_loads_without_the_token_and_the_data_does_not(project: Path) -> None:
    """The bug that made a token unusable in a browser: a page opened as `/?token=…` asks for
    `/app.js` with no query string, so guarding the bundle 401s the page's own script and the
    screen stays blank behind a URL that looked right. The exemption is the bundle only."""
    route = build(project, Policy(token="secret"))
    assert route(get("/app.js")).status == 200
    assert route(get("/style.css")).status == 200
    assert route(get("/api/board")).status == 401, "data still needs the token"
    assert route(get("/")).status == 401, "the app shell is not an asset"
    assert route(get("/api/app.js")).status == 401, "an api path is never an asset"


# ---- the access screen


def navigate(path: str, **query: str) -> Request:
    """What a BROWSER sends. The `Accept` header is the whole difference between a person and a
    script, and it is what decides whether a refusal renders or serialises."""
    return Request(method="GET", path=path, query=dict(query),
                   headers={"accept": "text/html,application/xhtml+xml,*/*;q=0.8"})


def test_a_browser_without_a_credential_gets_a_page_not_a_401(project: Path) -> None:
    """The point of the whole card: a link pasted into an address bar must offer a way IN, not a
    JSON error rendered as raw text."""
    route = build(project, Policy(token="secret"))
    reply = route(navigate("/"))
    assert reply.status == 200
    assert b"This board is locked" in reply.body
    assert reply.headers["Content-Type"].startswith("text/html")


def test_the_access_screen_is_served_for_any_spa_route(project: Path) -> None:
    """The UI routes in the browser, so a reload on a deep link is just as much a navigation as
    the root — and must not 401 either."""
    route = build(project, Policy(token="secret"))
    assert route(navigate("/task/tk-4f2a9c")).status == 200
    assert b"This board is locked" in route(navigate("/task/tk-4f2a9c")).body


def test_the_access_screen_serves_no_board_data(project: Path) -> None:
    """It replaces the refusal; it does not become a back door. Nothing that needed the token is
    reachable through it."""
    body = route_body(build(project, Policy(token="secret")), navigate("/"))
    assert b"Write the router" not in body and b"tk-" not in body


def test_the_access_screen_names_nothing_about_the_project(project: Path) -> None:
    """A caller who cannot prove a credential has no right to learn WHAT is behind it. The page
    carries the mount it was requested under — the caller's own URL echoed back, needed so the
    stored credential is keyed the way `api.ts` keys it — and nothing else."""
    route = build(project, Policy(token="secret"), base="/axion/")
    body = route_body(route, navigate("/"))
    assert body.count(b"axion") == 1, "only the <base> tag, which is the requested URL itself"
    assert b'<base href="/axion/">' in body
    assert str(project).encode() not in body, "no filesystem path"
    assert b"secret" not in body, "the token is never echoed"


def test_the_api_keeps_its_json_401_for_a_browser_too(project: Path) -> None:
    """`fetch` does not send `Accept: text/html`, but even if something did, an `/api/` path is an
    API call: its caller parses `code`, and HTML there would be a parse error instead of a
    message. The split is the path, not just the header."""
    route = build(project, Policy(token="secret"))
    refused = route(navigate("/api/board"))
    assert refused.status == 401
    assert body_of(refused)["code"] == "unauthorized"


def test_a_fetch_without_the_header_still_gets_the_error(project: Path) -> None:
    """A `curl` of the shell wants the refusal it can read, not a document."""
    assert build(project, Policy(token="secret"))(get("/")).status == 401


def test_a_valid_credential_serves_the_board_not_the_screen(project: Path) -> None:
    """The query form is the one a navigation can carry — a browser cannot attach an
    `Authorization` header to a link, which is exactly why the access screen re-enters that way."""
    route = build(project, Policy(token="secret"))
    reply = route(navigate("/", token="secret"))
    assert reply.status == 200
    assert b"This board is locked" not in reply.body


def test_a_local_ui_without_a_token_never_sees_the_screen(project: Path) -> None:
    """`taskops ui` on a laptop is open by design. No token set means no refusal to replace, so
    the access screen cannot appear where nothing is locked."""
    route = build(project, Policy())
    assert b"This board is locked" not in route(navigate("/")).body
    assert route(navigate("/api/board")).status == 200


def test_the_screen_replaces_only_a_missing_credential(project: Path) -> None:
    """A read-only refusal and a rate limit are answers to a caller who DID get in. Turning those
    into a login page would tell somebody to re-authenticate against a problem auth cannot fix."""
    route = build(project, Policy(readonly=True))
    refused = route(Request(method="POST", path="/api/comment", query={},
                            headers={"accept": "text/html"}, body=b"{}"))
    assert refused.status == 403 and body_of(refused)["code"] == "readonly"


def test_the_bundle_is_still_exempt_for_a_browser(project: Path) -> None:
    """The asset exemption runs inside the policy, so it is not reachable by the access screen at
    all — but the page's own reload depends on `app.js` still answering."""
    route = build(project, Policy(token="secret"))
    assert route(navigate("/app.js")).status == 200


def test_the_screen_stores_the_credential_where_the_bundle_reads_it(project: Path) -> None:
    """The page and `ui/src/api.ts` derive the SAME localStorage key from the SAME base. If this
    drifts, unlocking appears to work and the reload lands back on the lock screen."""
    body = route_body(build(project, Policy(token="secret")), navigate("/"))
    assert b'"taskops-token:" + base.pathname' in body
    source = (Path(__file__).parents[2] / "ui" / "src" / "api.ts").read_text(encoding="utf-8")
    assert "`taskops-token:${new URL(BASE).pathname}`" in source
    assert "localStorage.getItem(key)" in source, "the bundle reads storage, not only the URL"


def route_body(route: Any, request: Request) -> bytes:
    return route(request).body
