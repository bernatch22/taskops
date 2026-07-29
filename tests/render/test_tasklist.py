"""The task list render, from LITERALS — no project, no store, no git.

What the CLI test cannot say cheaply is what a hundred finished cards look like. Here a
board is a dict, so the cap is one assertion instead of a hundred `tasks add` calls.
"""

from __future__ import annotations

from taskops._types import STATUSES
from taskops.contracts import Board, Card, Column, Task
from taskops.render import render_tasklist
from tests.conftest import CLOCK


def a_board(**counts: int) -> Board:
    """`counts[status]` cards per column, each titled with its index so order is visible."""
    columns = [Column(status=status,         # type: ignore[typeddict-item]
                      cards=[Card(task=_task(status, index), lease=None, blocked_by=0,
                                  blocks=0, commits=0)
                             for index in range(counts.get(status, 0))])
               for status in STATUSES]
    return Board(repo="/tmp/x", columns=columns, ready=counts.get("ready", 0),
                 total=sum(counts.values()))


def _task(status: str, index: int) -> Task:
    """`updated` walks backwards with the index, so card 0 is the most recent one."""
    return Task(id=f"tk-{index:06d}", title=f"card {index}", spec="s",
                status=status,               # type: ignore[typeddict-item]
                priority=2, parent=None, labels=[], files=[], created_by="dev:berna",
                assignee="", reviewer="", created=CLOCK, updated=CLOCK - index)


def test_the_closed_list_is_capped_and_says_how_many_are_left() -> None:
    """A finished project has hundreds of these. A reader who scrolls past forty of them to
    reach the summary stops opening the command; a count says the rest are there."""
    text = render_tasklist(a_board(done=25))
    assert "card 0" in text and "card 9" in text
    assert "card 10" not in text
    assert "+15 more" in text
    assert "25 closed" in text


def test_closed_cards_are_newest_updated_first() -> None:
    """Open cards are ordered by what to do next; a closed card has no next, so the useful
    order is when it stopped moving."""
    rows = [line for line in render_tasklist(a_board(done=3)).splitlines()
            if line.startswith("✓")]
    assert [row.split()[1] for row in rows] == ["tk-000000", "tk-000001", "tk-000002"]


def test_an_utterly_empty_board_still_says_so() -> None:
    """Nothing open AND nothing closed is the one case where the old sentence was right."""
    assert render_tasklist(a_board()) == "no open tasks (0 in total)"


def test_the_open_list_keeps_its_old_shape() -> None:
    """No heading over the only group on the page, and no closed count for cards not shown."""
    text = render_tasklist(a_board(ready=2))
    assert not text.startswith("#")
    assert text.endswith("2 open, 2 ready")
