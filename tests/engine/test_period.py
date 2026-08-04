"""A report over a RANGE of days: the window, the selectors, and the by-day grouping.

The day report already promises not to move. This is the same promise over a wider window,
and the assertions are about the two ways a range can lie: by including a day it was not
asked for, and by leaving one out. A card closed the day BEFORE a range is the test that
matters — it is the one a rolling window would have swept in.
"""

from __future__ import annotations

import pytest

from taskops._errors import BadRequest
from taskops.contracts import ActorRoll, ClosedCard, CommitStat, PeriodReport, Task
from taskops.engine.calendar import shift, window
from taskops.engine.day import MAX_CLOSED, first_date, label_of, period_report
from taskops.render import render_day
from taskops.storage import Store
from taskops.usecases._range import Selector, resolve
from tests.engine.test_day import _log, _task

FIRST, LAST = "2026-07-22", "2026-07-28"

BEFORE = "2026-07-21"


def _closed_on(store: Store, task_id: str, date: str) -> None:
    """A card that reached `done` at noon of `date`."""
    start, _ = window(date)
    _task(store, task_id)
    _log(store, task_id, "agent:berna/v22", "claimed", start + 100.0)
    _log(store, task_id, "agent:berna/v22", "done", start + 43_200.0, to="done")


def test_both_ends_of_the_range_are_INSIDE_it(store: Store) -> None:
    """The first and the last day are days of the report, not its fenceposts. A window that
    ran to the last day's midnight would drop everything somebody did on it."""
    _closed_on(store, "tk-first", FIRST)
    _closed_on(store, "tk-last", LAST)
    report = period_report(store, FIRST, LAST)
    assert sorted(c["task"]["id"] for c in report["closed"]) == ["tk-first", "tk-last"]


def test_the_day_before_the_range_is_NOT_in_it(store: Store) -> None:
    """The whole point of a bounded window. A rolling "last 7 days" run at 09:00 keeps the
    tail of the day before it; this cuts at midnight, so the report is the same tomorrow."""
    _closed_on(store, "tk-early", BEFORE)
    _closed_on(store, "tk-in", FIRST)
    report = period_report(store, FIRST, LAST)
    assert [c["task"]["id"] for c in report["closed"]] == ["tk-in"]


def test_a_range_that_runs_backwards_is_refused(store: Store) -> None:
    with pytest.raises(BadRequest) as raised:
        period_report(store, LAST, FIRST)
    assert "forwards" in str(raised.value)


def test_one_day_is_the_same_object_as_a_range_of_one(store: Store) -> None:
    """`day_report` is `period_report` with both ends equal, and the label proves it did not
    grow a second shape on the way."""
    _closed_on(store, "tk-1", LAST)
    assert period_report(store, LAST, LAST)["label"] == LAST
    assert label_of(FIRST, LAST) == f"{FIRST}..{LAST}"


# ---- report all


def test_all_starts_at_the_FIRST_event_in_the_log(store: Store) -> None:
    """`report all` answers "evaluate everything done here", so its start is the log's own
    beginning — not a guess, and not a fixed number of days back."""
    _closed_on(store, "tk-early", BEFORE)
    _closed_on(store, "tk-late", LAST)
    start, end, label = resolve(store, Selector(whole=True, to=LAST))
    assert (start, label) == (BEFORE, "all")
    assert sorted(c["task"]["id"] for c in period_report(store, start, end, label)["closed"]) \
        == ["tk-early", "tk-late"]


def test_a_log_with_nothing_in_it_still_answers(store: Store) -> None:
    """An empty project reports today rather than raising — `report all` on a repo somebody
    just initialised is a fair question with a short answer."""
    assert len(first_date(store)) == 10


def test_all_is_labelled_all_and_not_by_its_dates(store: Store) -> None:
    """The label names the FILE. Dating it would leave a trail of near-identical `all`
    reports whose end date happens to differ, instead of one that is kept up to date."""
    _closed_on(store, "tk-1", LAST)
    assert resolve(store, Selector(whole=True))[2] == "all"


# ---- the selectors


@pytest.mark.parametrize(("last", "start"), [("7d", "2026-07-22"), ("1d", "2026-07-28"),
                                            ("2w", "2026-07-15"), ("1m", "2026-06-29")])
def test_a_relative_span_is_inclusive_of_both_ends(store: Store, last: str,
                                                   start: str) -> None:
    """`--last 7d` is seven days of work, ending today. Counting seven days BACK from today
    and keeping today too would quietly report eight."""
    assert resolve(store, Selector(last=last, to=LAST))[:2] == (start, LAST)


@pytest.mark.parametrize("bad", ["3fortnights", "7", "d", "0d", "-3d", "7 days"])
def test_a_span_nobody_can_read_is_refused_with_the_legal_forms(store: Store,
                                                                bad: str) -> None:
    """Never silently widened. A report covering the wrong month looks exactly like a correct
    one, and the error has to say what WOULD have worked or it just gets retried."""
    with pytest.raises(BadRequest) as raised:
        resolve(store, Selector(last=bad))
    assert "d, w or m" in str(raised.value) and "7d" in str(raised.value)


def test_from_without_to_runs_to_today(store: Store) -> None:
    start, end, _ = resolve(store, Selector(date=FIRST))
    assert start == FIRST and end == start  # a lone date is ONE day
    assert resolve(store, Selector(date=FIRST, to=""))[1] == FIRST


def test_an_explicit_pair_is_taken_as_given(store: Store) -> None:
    assert resolve(store, Selector(date=FIRST, to=LAST))[:2] == (FIRST, LAST)


def test_shift_crosses_a_month_boundary_by_the_calendar() -> None:
    """`mktime` owns the calendar. Hand-rolled arithmetic is where a 30-day month becomes 31
    for a week every year."""
    assert shift("2026-03-01", days=-1) == "2026-02-28"
    assert shift("2026-01-15", months=-1) == "2025-12-15"


# ---- rendering a range


def _report(from_date: str, to_date: str, **over: object) -> PeriodReport:
    """A literal report. The renderer is pure, so a range can be drawn without a database."""
    base = PeriodReport(repo="/x", from_date=from_date, to_date=to_date,
                        label=label_of(from_date, to_date), closed=[], dropped=0,
                        opened=[], in_flight=[], blocked=[], waiting=[], conversations=[],
                        actors=[ActorRoll(actor="dev:berna", tasks=1, commits=0,
                                          comments=0, done=0)],
                        commits_total=0)
    base.update(over)  # type: ignore[typeddict-item]
    return base


def test_a_range_groups_its_closed_cards_by_day_newest_first(store: Store) -> None:
    """A month under one heading is a wall nobody scrolls. Newest day first because the
    question a range answers is usually "and then what happened"."""
    _closed_on(store, "tk-early", FIRST)
    _closed_on(store, "tk-late", LAST)
    text = render_day(period_report(store, FIRST, LAST))
    assert text.index(f"### {LAST}") < text.index(f"### {FIRST}")
    assert text.index(f"### {LAST}") < text.index("tk-early")


def test_ONE_day_gets_no_day_headings(store: Store) -> None:
    """A `### 2026-07-28` under a `# 2026-07-28` title is noise, and its absence is what
    keeps a day's dossier byte-identical to what it always was."""
    _closed_on(store, "tk-1", LAST)
    assert "### " not in render_day(period_report(store, LAST, LAST))


def test_a_capped_range_says_how_many_cards_it_is_not_showing() -> None:
    """Never a silent truncation: a month that closed 400 cards and shows 200 of them is a
    fine report and a terrible lie."""
    text = render_day(_report(FIRST, LAST, dropped=7))
    assert "7 more card(s)" in text and "not shown" in text


def test_nothing_is_dropped_when_the_cap_is_not_reached() -> None:
    assert "not shown" not in render_day(_report(FIRST, LAST))
    assert MAX_CLOSED > 0


def test_ONE_days_dossier_is_BYTE_identical_to_what_it_always_was() -> None:
    """The golden. `report day` predates this card and people have the files committed; a
    generalisation that reformatted them would turn every past dossier into a diff.

    Byte for byte, from a literal report — which is only possible because `render` is pure.
    """
    # `milestone=""` completes the contract's new required field; the rendered bytes below are
    # unchanged, which is the point — a report is about what closed, not about which chapter.
    task = Task(id="tk-1", title="The work", spec="", status="done", priority=2, milestone="",
                parent=None,
                labels=[], files=[], assignee="", reviewer="", created_by="dev:berna", created=1.0,
                updated=1.0)
    card = ClosedCard(task=task, actor="agent:berna/v22", claimed_ts=0.0, done_ts=600.0,
                      commits=[CommitStat(sha="a" * 40, subject="did it", files=["src/x.py"],
                                          actor="agent:berna/v22", ts=1.0, additions=3,
                                          deletions=1)])
    day = _report("2026-07-28", "2026-07-28", closed=[card], commits_total=1,
                  actors=[ActorRoll(actor="agent:berna/v22", tasks=1, commits=1, comments=0,
                                    done=1)])
    assert render_day(day) == (
        "# 2026-07-28 — 1 closed · 0 in flight · 0 blocked · 1 commit(s) · 1 actor(s)\n"
        "\n## Cerrado (1)\n"
        "\n✓ **tk-1** — The work\n"
        "  agent:berna/v22 · held 10m · 1 commit(s) · +3 -1\n"
        "  `aaaaaaaaaaaa` did it (+3 -1)\n"
        "    src/x.py\n"
        "\n## Por actor\n"
        "\n| actor | tasks | commits | comments | closed |\n"
        "|---|---|---|---|---|\n"
        "| agent:berna/v22 | 1 | 1 | 0 | 1 |")


def test_an_empty_day_still_says_day_and_an_empty_range_says_window() -> None:
    """Same golden discipline on the quiet case: `report day` has always answered "Nothing
    happened on this day", and a range saying that would be reporting the wrong unit."""
    assert render_day(_report("2026-07-28", "2026-07-28", actors=[])).endswith(
        "Nothing happened on this day.")
    assert render_day(_report(FIRST, LAST, actors=[])).endswith(
        "Nothing happened in this window.")


# ---- a window that only planned


def _created(store: Store, task_id: str, date: str, status: str = "ready") -> None:
    """A card created at noon of `date`, in whatever state planning left it."""
    start, _ = window(date)
    _task(store, task_id, status=status)
    _log(store, task_id, "dev:berna", "created", start + 43_200.0)


def test_cards_only_CREATED_in_the_window_are_reported(store: Store) -> None:
    """The bug: four cards planned with specs and a dependency chain, and the report said
    `0 closed · 0 in flight · 0 blocked` over three empty headings, because `ready` and
    `backlog` belonged to no section at all."""
    _created(store, "tk-ready", LAST)
    _created(store, "tk-later", LAST, status="backlog")
    store.deps.add("tk-ready", "tk-later")

    report = period_report(store, LAST, LAST)

    assert [c["task"]["id"] for c in report["opened"]] == ["tk-ready", "tk-later"]
    assert report["opened"][1]["waiting_on"] == ["tk-ready"]
    assert report["opened"][0]["blocking"] == ["tk-later"]
    assert "Nothing happened" not in render_day(report)


def test_a_card_created_AND_closed_in_the_window_is_only_in_closed(store: Store) -> None:
    """`closed` already tells that story with its commits and its conversation. Listing it
    in both sections would invite a reader to count it twice."""
    _closed_on(store, "tk-1", LAST)
    _log(store, "tk-1", "dev:berna", "created", window(LAST)[0] + 50.0)
    report = period_report(store, LAST, LAST)
    assert report["opened"] == [] and len(report["closed"]) == 1


def test_an_unstarted_card_touched_but_not_created_lands_in_waiting(store: Store) -> None:
    """Neither working nor blocked, so nothing rendered it — and `opened` must not claim the
    window created it either."""
    _created(store, "tk-old", BEFORE, status="backlog")
    _log(store, "tk-old", "dev:berna", "comment", window(LAST)[0] + 100.0, text="bump")
    report = period_report(store, LAST, LAST)
    assert [t["id"] for t in report["waiting"]] == ["tk-old"] and report["opened"] == []
