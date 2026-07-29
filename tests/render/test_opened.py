"""A window that only PLANNED still reports what it planned.

The bug these pin: four cards created with specs, files and a dependency chain, and
`taskops report all` answered `0 closed · 0 in flight · 0 blocked` over three empty headings.
`in_flight` filtered the working statuses and `blocked` filtered `blocked`, so `backlog` and
`ready` — which is ALL planned-but-unstarted work — belonged to no section and were rendered
nowhere. The same class of bug as a finished project answering `tasks list` with silence.

Pure, from a literal report: no database, no git.
"""

from __future__ import annotations

from taskops.contracts import ActorRoll, OpenedCard, PeriodReport, Task
from taskops.render import render_day

SPEC = "What done looks like, in the ask's own words."


def _task(task_id: str, status: str = "ready", **over: object) -> Task:
    base = Task(id=task_id, title=f"Card {task_id}", spec=SPEC, status=status,  # type: ignore[typeddict-item]
                priority=1, parent=None, labels=["backend"], files=["db/schema.sql"],
                assignee="", reviewer="", created_by="dev:berna", created=1.0, updated=1.0)
    base.update(over)  # type: ignore[typeddict-item]
    return base


def _planning_day(**over: object) -> PeriodReport:
    """A day whose entire content is four cards created and a dependency chain."""
    opened = [OpenedCard(task=_task("tk-a"), waiting_on=[], blocking=["tk-b"]),
              OpenedCard(task=_task("tk-b", status="backlog"), waiting_on=["tk-a"],
                         blocking=[])]
    base = PeriodReport(repo="/x", from_date="2026-07-28", to_date="2026-07-28",
                        label="2026-07-28", closed=[], dropped=0, opened=opened,
                        in_flight=[], blocked=[], waiting=[], conversations=[],
                        actors=[ActorRoll(actor="dev:berna", tasks=2, commits=0,
                                          comments=0, done=0)],
                        commits_total=0)
    base.update(over)  # type: ignore[typeddict-item]
    return base


def test_a_day_that_only_PLANNED_still_says_what_it_planned() -> None:
    """The bug, exactly: cards created and none closed rendered as nothing at all."""
    text = render_day(_planning_day())
    assert "## Abierto (2)" in text
    assert "tk-a" in text and "tk-b" in text
    assert "Nothing happened" not in text


def test_the_DAG_is_on_the_page_because_it_is_the_content_of_a_planning_day() -> None:
    """"What can I start now" and "what is waiting on what" are the only questions such a day
    can answer, and a list of titles answers neither."""
    text = render_day(_planning_day())
    assert "listo para empezar" in text, "the card with no open blocker says so out loud"
    assert "espera a: tk-a" in text
    assert "bloquea a: tk-b" in text


def test_the_headline_counts_what_it_now_shows() -> None:
    """Otherwise the summary line keeps claiming the window was empty while listing four
    cards underneath it."""
    assert render_day(_planning_day()).startswith("# 2026-07-28 — 0 closed · 2 opened")


def test_the_counts_it_does_NOT_show_stay_off_the_headline() -> None:
    """`opened` and `waiting` are printed only when non-zero, which is what keeps every
    dossier ever committed carrying the header it was written with."""
    quiet = render_day(_planning_day(opened=[], waiting=[], commits_total=1))
    assert "opened" not in quiet and "waiting" not in quiet


def test_ready_and_backlog_touched_but_not_created_get_their_own_section() -> None:
    """They were dropped on the floor: neither working nor blocked, so no section held them."""
    text = render_day(_planning_day(opened=[], waiting=[_task("tk-old", status="backlog")]))
    assert "## Sigue abierto" in text and "tk-old" in text


def test_the_written_report_carries_an_opened_cards_SPEC_too() -> None:
    """Same rule as the closed cards: what was ASKED has to be in the document."""
    assert SPEC in render_day(_planning_day(), detail="full")
    assert SPEC not in render_day(_planning_day())


def test_a_window_with_NOTHING_in_any_section_says_so_in_one_line() -> None:
    """And says which window. Judged on the sections and not on `actors` — it was judged on
    actors, which is exactly how the planning day hid: four cards created is one actor with
    four tasks, so the report was not "empty", it just had nothing that could hold them."""
    text = render_day(_planning_day(opened=[], actors=[]))
    assert text == "# 2026-07-28\n\nNothing happened on this day."
