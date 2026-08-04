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
from taskops.engine.calendar import window
from taskops.engine.day import day_report
from taskops.engine.diffstat import numstats, parse
from taskops.storage import Store

DATE = "2026-07-28"


def _log(store: Store, task: str, actor: str, kind: str, ts: float,
         **body: object) -> None:
    record(store, task=task, actor=actor, kind=kind, body=body, ts=ts)


def _task(store: Store, task_id: str, status: str = "done") -> None:
    store.tasks.insert(Task(id=task_id, title=f"Work {task_id}", spec="", status=status,
                            # `milestone` is required by the contract now; the fixture completes
                            # it. A day's report is about what closed, not about the chapter.
                            priority=2, milestone="", parent=None, labels=[], files=[],
                            assignee="", reviewer="",
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
    from taskops.engine.calendar import date_of

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
    """The assertions are untouched; the FIXTURE gained the two events the log always had.

    It set `status` on the task row and logged nothing that said so, which no real path can do —
    every route to `claimed` or `blocked` records its move (`claim._take`, `_transition.move`).
    Sections are now decided by what the window's log SAYS, so a row stamped by hand behind the
    log's back is a state the system cannot reach, and the fixture is what was wrong.

    Note the second event: kind `blocked` is a DEPENDENCY EDGE, not a status. The card reaches
    the `blocked` STATUS through a `status` event, and conflating the two would report every
    card that ever gained a blocker as blocked on the day it gained it.
    """
    start, _ = window(DATE)
    _task(store, "tk-1", status="claimed")
    _task(store, "tk-2", status="blocked")
    _log(store, "tk-1", "agent:berna/v22", "claimed", start + 5.0, to="claimed")
    _log(store, "tk-1", "agent:berna/v22", "commit", start + 10.0, sha="a" * 40,
         subject="first", files=["src/x.py"])
    _log(store, "tk-2", "agent:berna/v22", "blocked", start + 20.0)
    _log(store, "tk-2", "agent:berna/v22", "status", start + 21.0, to="blocked")
    report = day_report(store, DATE)
    assert report["commits_total"] == 1
    assert [t["id"] for t in report["in_flight"]] == ["tk-1"]
    assert [t["id"] for t in report["blocked"]] == ["tk-2"]


def test_a_card_created_here_and_closed_LATER_stays_in_this_day_s_plan(store: Store) -> None:
    """The regression that made a regenerated dossier report less than the original.

    `opened` filtered on the card's status AS OF NOW, so a card planned on Tuesday and finished
    on Thursday disappeared from Tuesday's report — and Tuesday's `closed` never held it either,
    because it closed on Thursday. On the axion board 2026-07-30 fell from `5 opened` to `3` to
    `2` over three regenerations, one line of that day's planning lost per card that closed.
    """
    start, _ = window(DATE)
    _task(store, "tk-1", status="done")            # closed two days after this window
    _log(store, "tk-1", "dev:berna", "created", start + 10.0, title="Work tk-1")
    _log(store, "tk-1", "dev:berna", "done", start + 200_000.0, to="done")

    report = day_report(store, DATE)
    assert [c["task"]["id"] for c in report["opened"]] == ["tk-1"]
    assert [c["task"]["id"] for c in report["closed"]] == [], "it did not close on this day"


def test_a_card_created_AND_closed_here_is_only_in_the_closed_section(store: Store) -> None:
    """`closed` already tells that card's whole story with its commits and its conversation.
    Printing it under `Abierto` too invites a reader to count it twice."""
    start, _ = window(DATE)
    _task(store, "tk-1", status="done")
    _log(store, "tk-1", "dev:berna", "created", start + 10.0, title="Work tk-1")
    _log(store, "tk-1", "dev:berna", "done", start + 20.0, to="done")

    report = day_report(store, DATE)
    assert [c["task"]["id"] for c in report["closed"]] == ["tk-1"]
    assert report["opened"] == []


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


def test_a_card_in_flight_here_and_closed_LATER_stays_in_THIS_day_s_in_flight(
        store: Store) -> None:
    """The same regression as `opened`, one section down — and the reason for this card.

    `in_flight`/`blocked`/`waiting` filtered on the status the card holds NOW, so a card claimed
    on Tuesday and finished on Thursday was in no Tuesday section at all by Friday: not in
    flight (it is done), and not in Tuesday's `closed` either (it closed on Thursday). It is
    now sorted by the status it held when the window CLOSED, which the log can answer.
    """
    start, _ = window(DATE)
    _task(store, "tk-1", status="done")             # finished two days after this window
    _log(store, "tk-1", "agent:berna/v22", "claimed", start + 10.0, to="claimed")
    _log(store, "tk-1", "dev:berna", "done", start + 200_000.0, to="done")

    report = day_report(store, DATE)
    assert [t["id"] for t in report["in_flight"]] == ["tk-1"]
    assert [c["task"]["id"] for c in report["closed"]] == [], "it did not close on this day"


def test_a_card_BLOCKED_here_and_since_unblocked_stays_blocked_for_this_day(store: Store) -> None:
    """A blocker cleared on Thursday does not make Tuesday's morning un-blocked."""
    start, _ = window(DATE)
    _task(store, "tk-1", status="claimed")
    _log(store, "tk-1", "dev:berna", "status", start + 10.0, to="blocked")
    _log(store, "tk-1", "dev:berna", "status", start + 300_000.0, to="claimed")

    report = day_report(store, DATE)
    assert [t["id"] for t in report["blocked"]] == ["tk-1"]
    assert report["in_flight"] == []


def test_a_transition_stamped_ON_the_boundary_belongs_to_the_NEXT_day(store: Store) -> None:
    """The window's upper edge is exclusive, so two consecutive dossiers cannot both claim one
    move. A card claimed at exactly the next midnight was still unstarted all of this day."""
    start, end = window(DATE)
    _task(store, "tk-1", status="claimed")
    _log(store, "tk-1", "dev:berna", "comment", start + 10.0, text="planning it")
    _log(store, "tk-1", "agent:berna/v22", "claimed", end, to="claimed")

    report = day_report(store, DATE)
    assert report["in_flight"] == []
    assert [t["id"] for t in report["waiting"]] == ["tk-1"]


def test_a_regenerated_day_reports_the_SAME_sections_after_everything_closes(
        store: Store) -> None:
    """The property the whole thread is about, asserted as a property rather than a case.

    A window is a claim about the past, so generating it today and generating it after every
    card has closed must produce the same four sections. This is what failed on the axion board:
    2026-07-30 fell from `5 opened` to `3` to `2` over three regenerations.
    """
    start, _ = window(DATE)
    # tk-1 and tk-2 were planned EARLIER and are worked on today, which is what the moving
    # sections describe; tk-4 is planned today, so it belongs to `opened` and to nothing else.
    for n, kind in ((1, "claimed"), (2, "blocked")):
        _task(store, f"tk-{n}", status=kind)
        _log(store, f"tk-{n}", "dev:berna", "created", start - 100_000.0, title=f"Work tk-{n}")
        _log(store, f"tk-{n}", "dev:berna", "status", start + 10.0 + n, to=kind)
    _task(store, "tk-3", status="ready")
    _log(store, "tk-3", "dev:berna", "comment", start + 30.0, text="not started")
    _task(store, "tk-4", status="ready")
    _log(store, "tk-4", "dev:berna", "created", start + 40.0, title="Work tk-4")

    before = day_report(store, DATE)
    for n in (1, 2, 3, 4):                     # the whole day's work closes, days later
        store.tasks.set_status(f"tk-{n}", "done", when=start + 400_000.0)
        _log(store, f"tk-{n}", "dev:berna", "done", start + 400_000.0, to="done")
    after = day_report(store, DATE)

    for section in ("opened", "in_flight", "blocked", "waiting"):
        assert _ids(after[section]) == _ids(before[section]), f"{section} shrank on regeneration"
    assert _ids(before["in_flight"]) == ["tk-1"]
    assert _ids(before["blocked"]) == ["tk-2"]
    assert _ids(before["waiting"]) == ["tk-3"], "tk-4 is in `opened`, so not here too"
    assert _ids(before["opened"]) == ["tk-4"]


def _ids(section: list[object]) -> list[str]:
    """Ids out of either shape a section can hold — `OpenedCard` wraps its task, the rest are
    bare tasks. One helper so the property above reads as one loop over four sections."""
    out = []
    for row in section:
        item = row["task"] if isinstance(row, dict) and "task" in row else row
        out.append(str(item["id"]))                    # type: ignore[index]
    return out


def test_a_card_planned_AND_claimed_here_is_in_ONE_section(store: Store) -> None:
    """`render/day` states "EVERY open card lands in exactly one section". It was not true.

    The exclusion of the window's own new cards lived only in `waiting`, so a card planned and
    claimed on the same day was printed under `## Abierto` and again under `## Sigue abierto`.
    Found by running `report day` on a scratch board, not by reading the code.
    """
    start, _ = window(DATE)
    _task(store, "tk-1", status="claimed")
    _log(store, "tk-1", "dev:berna", "created", start + 10.0, title="Work tk-1")
    _log(store, "tk-1", "agent:berna/w1", "claimed", start + 20.0, to="claimed")

    report = day_report(store, DATE)
    assert [c["task"]["id"] for c in report["opened"]] == ["tk-1"], "the window planned it"
    assert report["in_flight"] == [], "and must not print it a second time"
    assert report["blocked"] == [] and report["waiting"] == []
