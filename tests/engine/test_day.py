"""The daily dossier: a CALENDAR day, and the arithmetic that makes it one.

The whole value of this report over a standup is that it does not move. Every assertion here
is about that promise — the window cuts where the reader's calendar cuts, a card is filed
under the day it CLOSED, and a repository git cannot read produces zeros rather than an
exception in the middle of somebody's morning.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskops._errors import BadRequest
from taskops.contracts import Task
from taskops.engine import record
from taskops.engine.day import day_report, window
from taskops.engine.diffstat import numstats, parse
from taskops.storage import Store

DATE = "2026-07-28"


def _log(store: Store, task: str, actor: str, kind: str, ts: float,
         **body: object) -> None:
    record(store, task=task, actor=actor, kind=kind, body=body, ts=ts)


def _task(store: Store, task_id: str, status: str = "done") -> None:
    store.tasks.insert(Task(id=task_id, title=f"Work {task_id}", spec="", status=status,
                            priority=2, parent=None, labels=[], files=[], assignee="", reviewer="",
                            created_by="dev:berna", created=1.0, updated=1.0))


def test_the_window_is_the_local_calendar_day() -> None:
    """Midnight to midnight in the reader's own zone, and never a fixed 86 400.

    `start + 86400` is wrong twice a year — on the day the clocks change it either loses an
    hour of somebody's work or borrows one from the next day, and both land in a report
    people compare against yesterday's.
    """
    start, end = window(DATE)
    assert end > start
    assert (end - start) in (82_800.0, 86_400.0, 90_000.0)


def test_a_date_that_is_not_one_is_refused_with_the_shape_it_wanted() -> None:
    with pytest.raises(BadRequest) as raised:
        window("last tuesday")
    assert "YYYY-MM-DD" in str(raised.value)


def test_a_card_closed_after_midnight_belongs_to_the_CLOSING_day(store: Store) -> None:
    """Claimed at 23:50, closed at 00:10. The work spans two dates and the CLOSE decides.

    Filing it under the claim would make a day's report depend on when somebody started,
    which is unknowable from the outside — "what closed today" is the question, and a card
    can only close once.
    """
    first, midnight = window(DATE)
    _task(store, "tk-1")
    _log(store, "tk-1", "agent:berna/v22", "claimed", midnight - 600.0)
    _log(store, "tk-1", "agent:berna/v22", "done", midnight + 600.0, to="done")

    assert [c["task"]["id"] for c in day_report(store, DATE)["closed"]] == []
    tomorrow = day_report(store, _next_date(midnight))
    assert [c["task"]["id"] for c in tomorrow["closed"]] == ["tk-1"]
    assert first < tomorrow["closed"][0]["claimed_ts"] < tomorrow["closed"][0]["done_ts"]


def _next_date(midnight: float) -> str:
    from taskops.engine.day import date_of

    return date_of(midnight + 3600.0)


def test_the_window_cuts_at_midnight_and_not_24_hours_back(store: Store) -> None:
    """A rolling window run at 09:00 would keep yesterday evening. This must not."""
    start, end = window(DATE)
    _log(store, "tk-1", "dev:berna", "comment", start - 60.0, text="yesterday")
    _log(store, "tk-1", "dev:berna", "comment", start + 60.0, text="this morning")
    _log(store, "tk-1", "dev:berna", "comment", end + 60.0, text="tomorrow")
    said = [e["body"]["text"] for e in day_report(store, DATE)["conversations"]]
    assert said == ["this morning"]


def test_an_event_exactly_at_midnight_is_INSIDE_the_day(store: Store) -> None:
    """[00:00, 24:00). The half-open interval is what stops one event landing on two days —
    or, with both ends exclusive, on neither."""
    start, _ = window(DATE)
    _log(store, "tk-1", "dev:berna", "comment", start, text="on the stroke")
    assert len(day_report(store, DATE)["conversations"]) == 1


def test_heartbeats_never_reach_the_dossier(store: Store) -> None:
    """`activity` is a per-tool-call heartbeat. A busy day has thousands, and counting them
    would rank the agent with the plugin installed above the one that closed four cards."""
    start, _ = window(DATE)
    for index in range(50):
        _log(store, "tk-1", "agent:berna/v22", "activity", start + index, summary="ls")
    _log(store, "tk-1", "dev:berna", "comment", start + 100.0, text="hi")
    report = day_report(store, DATE)
    assert [roll["actor"] for roll in report["actors"]] == ["dev:berna"]


def test_the_day_counts_commits_and_shows_what_is_still_open(store: Store) -> None:
    start, _ = window(DATE)
    _task(store, "tk-1", status="in_progress")
    _task(store, "tk-2", status="blocked")
    _log(store, "tk-1", "agent:berna/v22", "commit", start + 10.0, sha="a" * 40,
         subject="first", files=["src/x.py"])
    _log(store, "tk-2", "agent:berna/v22", "blocked", start + 20.0)
    report = day_report(store, DATE)
    assert report["commits_total"] == 1
    assert [t["id"] for t in report["in_flight"]] == ["tk-1"]
    assert [t["id"] for t in report["blocked"]] == ["tk-2"]


def test_a_closed_card_carries_its_commits_with_their_sizes(store: Store) -> None:
    """The commit event already held the subject and the files; only the diff size is new."""
    start, _ = window(DATE)
    _task(store, "tk-1")
    _log(store, "tk-1", "agent:berna/v22", "commit", start + 10.0, sha="a" * 40,
         subject="the work", files=["src/x.py"])
    _log(store, "tk-1", "agent:berna/v22", "done", start + 20.0, to="done")
    commit = day_report(store, DATE)["closed"][0]["commits"][0]
    assert commit["subject"] == "the work"
    assert (commit["additions"], commit["deletions"]) == (0, 0)


# ---- the numstat batch


def test_numstat_totals_a_commit_across_its_files() -> None:
    """The `--numstat` stream, from a literal string. Building real commits to assert on
    arithmetic would test git, and slowly."""
    out = "abc123\n\n1\t2\tsrc/x.py\n3\t4\tsrc/y.py\ndef456\n\n5\t0\tREADME.md\n"
    assert parse(out) == {"abc123": (4, 6), "def456": (5, 0)}


def test_a_binary_file_contributes_nothing_instead_of_breaking_the_parse() -> None:
    """git reports `-` for both counts on a binary blob. That is not zero, but zero is the
    only number that can be summed — and a dossier that raised on a PNG would be useless."""
    assert parse("abc123\n\n-\t-\tlogo.png\n2\t1\tsrc/x.py\n") == {"abc123": (2, 1)}


def test_a_commit_with_no_files_still_appears_at_zero() -> None:
    """An empty commit is a fact about the day, not an absence. Dropping it would make the
    card's commit count and its diff list disagree."""
    assert parse("abc123\n\n") == {"abc123": (0, 0)}


def test_sizes_degrade_to_nothing_where_there_is_no_git(tmp_path: Path) -> None:
    """Same rule as the rest of `gitio`: a report is never worth an exception. A shallow
    clone, a garbage-collected sha and a directory that is not a repository all land here."""
    assert numstats(tmp_path, ["a" * 40]) == {}
    assert numstats(tmp_path, []) == {}
