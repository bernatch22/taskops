"""The replication endpoints: events in both directions, and the report file's no-clobber rule.

Pure `Request -> Reply` calls like the rest of the HTTP suite — no port, no thread. What is
tested here is the CONTRACT another taskops codes against, so a rename in these payloads is a
break for a client this repository cannot see.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from taskops.engine import stamp
from taskops.transports.http._wire import Reply, Request
from taskops.transports.http.policy import Policy
from taskops.transports.http.router import build
from taskops.usecases import init, plan
from taskops.usecases.milestone import open_chapter


def get(path: str, **query: str) -> Request:
    return Request(method="GET", path=path, query=dict(query), headers={})


def send(method: str, path: str, payload: dict[str, Any]) -> Request:
    return Request(method=method, path=path, query={}, headers={},
                   body=json.dumps(payload).encode())


def body_of(reply: Reply) -> Any:
    return json.loads(reply.body)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    # Every card belongs to a chapter: the fixture opens one so the test can be about its own
    # subject rather than about that.
    init(tmp_path, install_git_hooks=False)
    open_chapter(tmp_path, "the chapter these tests plan into",
                 actor="dev:berna")
    plan(tmp_path, [{"title": "Ship the exchange", "spec": "Events over HTTP.", "files": ["x.py"]}],
         actor="dev:berna")
    return tmp_path


@pytest.fixture
def route(project: Path) -> Any:
    return build(project, Policy())


def foreign(index: int, kind: str = "comment") -> dict[str, Any]:
    """An event as another machine would put it on the wire — with ITS id, which we keep."""
    return {"id": f"ev-foreign-{index}", "task": "tk-000000", "actor": "dev:ana",
            "kind": kind, "body": {"text": f"hello {index}"}, "ts": 1000.0 + index}


# ---- POST /api/sync


def test_a_batch_is_relayed_and_counted(route: Any) -> None:
    reply = route(send("POST", "/api/sync", {"events": [foreign(1), foreign(2)]}))
    assert reply.status == 200
    payload = body_of(reply)
    assert payload["accepted"] == 2
    assert payload["max_seq"] > 0


def test_the_same_batch_twice_accepts_nothing_the_second_time(route: Any) -> None:
    """THE idempotency signal. Ids are content hashes, so a retry is a no-op — and `accepted: 0`
    is how the client's log distinguishes a retry from importing everything twice."""
    batch = {"events": [foreign(1), foreign(2)]}
    route(send("POST", "/api/sync", batch))
    assert body_of(route(send("POST", "/api/sync", batch)))["accepted"] == 0


def test_a_foreign_id_is_kept_verbatim(route: Any) -> None:
    """Recomputing it would fork history the moment a newer taskops serializes a body field
    differently — so the pushed id must be the one that comes back out."""
    route(send("POST", "/api/sync", {"events": [foreign(7)]}))
    pulled = body_of(route(get("/api/sync", after="0")))["events"]
    assert "ev-foreign-7" in [event["id"] for event in pulled]


def test_local_only_kinds_are_dropped_rather_than_stored(route: Any) -> None:
    """A client should not send `activity` at all; a server does not trust it not to."""
    reply = route(send("POST", "/api/sync", {"events": [foreign(1, "activity"), foreign(2)]}))
    assert body_of(reply)["accepted"] == 1
    pulled = body_of(route(get("/api/sync", after="0")))["events"]
    assert "activity" not in [event["kind"] for event in pulled]


def test_a_malformed_event_names_its_index(route: Any) -> None:
    """The whole batch is refused, and the message says WHICH one — a 400 that does not is a
    client-side bisect over 500 events."""
    reply = route(send("POST", "/api/sync", {"events": [foreign(1), {"nope": True}]}))
    assert reply.status == 400
    assert "events[1]" in body_of(reply)["error"]


def test_a_refused_batch_stored_nothing(route: Any) -> None:
    """Coercion happens before any write, so index 0 is not left half-applied."""
    route(send("POST", "/api/sync", {"events": [foreign(1), {"nope": True}]}))
    pulled = body_of(route(get("/api/sync", after="0")))["events"]
    assert "ev-foreign-1" not in [event["id"] for event in pulled]


def test_an_oversized_batch_is_refused(route: Any) -> None:
    reply = route(send("POST", "/api/sync", {"events": [foreign(i) for i in range(501)]}))
    assert reply.status == 400
    assert "500" in body_of(reply)["error"]


def test_events_must_be_a_list(route: Any) -> None:
    assert route(send("POST", "/api/sync", {"events": "everything"})).status == 400


# ---- GET /api/sync


def test_the_cursor_pages_and_reports_more(route: Any) -> None:
    route(send("POST", "/api/sync", {"events": [foreign(i) for i in range(10)]}))
    first = body_of(route(get("/api/sync", after="0", limit="3")))
    assert len(first["events"]) == 3
    assert first["more"] is True
    second = body_of(route(get("/api/sync", after=str(first["max_seq"]), limit="3")))
    assert first["max_seq"] < second["max_seq"]
    assert not {e["id"] for e in first["events"]} & {e["id"] for e in second["events"]}


def test_the_last_page_says_there_is_no_more(route: Any) -> None:
    seen: set[str] = set()
    cursor, more = 0, True
    while more:
        page = body_of(route(get("/api/sync", after=str(cursor), limit="4")))
        seen |= {event["id"] for event in page["events"]}
        cursor, more = page["max_seq"], page["more"]
    route(send("POST", "/api/sync", {"events": [foreign(99)]}))
    tail = body_of(route(get("/api/sync", after=str(cursor))))
    assert [event["id"] for event in tail["events"]] == ["ev-foreign-99"]


def test_a_junk_cursor_is_the_beginning_not_a_500(route: Any) -> None:
    assert route(get("/api/sync", after="yesterday")).status == 200


# ---- the report file: GET


def written(root: Path, label: str, text: str) -> Path:
    path = root / ".taskops" / "reports" / f"{label}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def narration(seq: int, prose: str = "The day went well.") -> str:
    return f"{stamp('2026-07-28', seq, 0.0)}\n\n# 2026-07-28\n\n{prose}\n"


def test_a_report_is_served_with_its_stamp(route: Any, project: Path) -> None:
    written(project, "2026-07-28", narration(41))
    payload = body_of(route(get("/api/report/file", label="2026-07-28")))
    assert payload["label"] == "2026-07-28"
    assert payload["max_seq"] == 41
    assert "The day went well." in payload["content"]


def test_a_report_nobody_wrote_is_a_404_and_not_a_generated_one(route: Any) -> None:
    """The server never regenerates to answer. A client that got a fresh dossier here would
    believe there is something on this server to lose, and refuse to push its own narration."""
    reply = route(get("/api/report/file", label="2026-07-28"))
    assert reply.status == 404
    assert body_of(reply)["code"] == "no_such_report"


def test_a_label_cannot_escape_the_reports_directory(route: Any) -> None:
    reply = route(get("/api/report/file", label="../../../etc/passwd"))
    assert reply.status == 400


# ---- the report file: the five PUT cases


def put(label: str, content: str, force: bool = False) -> Request:
    return send("PUT", "/api/report/file",
                {"label": label, "content": content, "force": force})


def test_put_case_one_the_server_has_no_file_so_it_is_stored(route: Any, project: Path) -> None:
    reply = route(put("2026-07-28", narration(10)))
    assert reply.status == 200
    assert body_of(reply)["stored"] is True
    assert (project / ".taskops" / "reports" / "2026-07-28.md").is_file()


def test_put_case_two_a_higher_stamp_wins(route: Any, project: Path) -> None:
    """Generated over more of the log, so it is the later account of the same day."""
    written(project, "2026-07-28", narration(10, "Half a day."))
    assert route(put("2026-07-28", narration(20, "The whole day."))).status == 200
    assert "The whole day." in (project / ".taskops" / "reports" / "2026-07-28.md").read_text()


def test_put_case_three_a_lower_stamp_is_a_409_naming_both(route: Any, project: Path) -> None:
    written(project, "2026-07-28", narration(20, "The whole day."))
    reply = route(put("2026-07-28", narration(10, "Half a day.")))
    assert reply.status == 409
    payload = body_of(reply)
    assert payload["code"] == "report_conflict"
    assert (payload["ours"], payload["theirs"]) == (20, 10)
    assert "The whole day." in (project / ".taskops" / "reports" / "2026-07-28.md").read_text()


def test_put_case_four_equal_stamps_and_different_prose_always_conflict(
        route: Any, project: Path) -> None:
    """THE case the whole rule exists for: two narrations of one day, and prose cannot be
    merged. One of them may have been written by a person, so nobody here may pick."""
    written(project, "2026-07-28", narration(20, "Ana's account."))
    reply = route(put("2026-07-28", narration(20, "Berna's account.")))
    assert reply.status == 409
    assert (body_of(reply)["ours"], body_of(reply)["theirs"]) == (20, 20)
    assert "Ana's account." in (project / ".taskops" / "reports" / "2026-07-28.md").read_text()


def test_put_case_five_force_overwrites_and_the_refusal_said_what_is_lost(
        route: Any, project: Path) -> None:
    written(project, "2026-07-28", narration(20, "Ana's account."))
    assert "narration is then lost" in body_of(route(put("2026-07-28", narration(20, "x"))))["error"]
    assert route(put("2026-07-28", narration(20, "Berna's account."), force=True)).status == 200
    assert "Berna's account." in (project / ".taskops" / "reports" / "2026-07-28.md").read_text()


def test_an_identical_push_is_quiet(route: Any, project: Path) -> None:
    """Equal stamps AND equal bytes is the ordinary re-sync, not a conflict."""
    written(project, "2026-07-28", narration(20))
    assert route(put("2026-07-28", narration(20))).status == 200


def test_an_unstamped_file_is_never_clobbered_by_a_stamped_one(route: Any, project: Path) -> None:
    """No stamp means written or edited BY HAND — the copy with no second source anywhere.

    "Unknown" is not "older": a higher number cannot win against a file whose coverage nothing
    can measure, so this falls to the conflict, which is the honest answer.
    """
    written(project, "2026-07-28", "# 2026-07-28\n\nWritten by hand.\n")
    reply = route(put("2026-07-28", narration(99)))
    assert reply.status == 409
    assert body_of(reply)["ours"] == -1
    assert "by hand" in body_of(reply)["error"]


def test_a_put_without_content_is_a_400(route: Any) -> None:
    assert route(send("PUT", "/api/report/file", {"label": "2026-07-28"})).status == 400


# ---- the policy


def test_readonly_refuses_the_push_and_the_report_put(project: Path) -> None:
    """By METHOD, in the policy, before any of this runs — a board on a screen in a room cannot
    be written into, and that has to hold for endpoints the policy has never heard of."""
    route = build(project, Policy(readonly=True))
    assert route(send("POST", "/api/sync", {"events": []})).status == 403
    assert route(put("2026-07-28", narration(1))).status == 403
    assert route(get("/api/sync", after="0")).status == 200


def test_a_get_on_the_put_only_shape_still_lists_its_methods(route: Any) -> None:
    reply = route(send("DELETE", "/api/report/file", {}))
    assert reply.status == 405
    assert "PUT" in body_of(reply)["error"]


def test_a_pushed_card_appears_on_the_servers_board(tmp_path: Path) -> None:
    """Accepting events without materialising them is the bug the git path hit once: the log
    grows and the board stays empty. The server-side smoke caught the same hole here — the
    pushed card was in the events table and in none of the eight columns."""
    from taskops.engine import build
    from taskops.usecases import board, init
    from taskops.usecases.exchange import accept_events

    init(tmp_path, install_git_hooks=False)
    open_chapter(tmp_path, "the chapter these tests plan into",
                 actor="dev:berna")
    created = build(task="tk-9press", actor="dev:x", kind="created",
                    body={"title": "Pushed from afar", "spec": ""})
    result = accept_events(tmp_path, [dict(created)])
    assert result["accepted"] == 1
    titles = [c["task"]["title"] for col in board(tmp_path)["columns"] for c in col["cards"]]
    assert "Pushed from afar" in titles, "the event landed but the board never learned"
