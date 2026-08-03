"""The board render. Every column, always.

Hiding empty columns was the first version, on the theory that four of eight statuses are usually empty
and showing them turns a readable board into a row of placeholders. It reads as a BUG instead: somebody
who cannot see a `done` column cannot tell whether nothing is finished or whether the board has no such
state — and "where are my done cards" is the question it produced.

Rendered from LITERALS, with no database anywhere. That is the whole point of `render/` being pure: a
question about what the board shows is answerable without a project, a store, or a git repository.
"""

from __future__ import annotations

from taskops._types import STATUSES
from taskops.contracts import Board, Card, Column, Task
from taskops.render import render_board
from tests.conftest import CLOCK


def a_task(status: str, title: str = "T") -> Task:
    # `milestone=""` only completes a field `Task` gained in 0.5.0. No rendered byte below
    # changes: nothing here reads the chapter.
    return Task(id="tk-aaaaaa", title=title, spec="s",
                status=status,               # type: ignore[typeddict-item]
                priority=2, milestone="", parent=None, labels=[], files=[],
                created_by="dev:berna",
                assignee="", reviewer="", created=CLOCK, updated=CLOCK)


def a_board(**counts: int) -> Board:
    """A board with `counts[status]` cards in each column, and none in the rest."""
    columns = [Column(status=status,         # type: ignore[typeddict-item]
                      cards=[Card(task=a_task(status), lease=None, blocked_by=0,
                                  blocks=0, commits=0)
                             for _ in range(counts.get(status, 0))])
               for status in STATUSES]
    return Board(repo="/tmp/x", columns=columns, ready=counts.get("ready", 0),
                 total=sum(counts.values()))


def test_every_status_gets_a_heading_even_with_no_cards() -> None:
    text = render_board(a_board(ready=2))
    for status in STATUSES:
        assert f"{status} (" in text, f"{status} has no heading"


def test_an_empty_column_says_it_is_empty() -> None:
    """A bare gap under a heading reads as something that failed to load."""
    text = render_board(a_board(ready=1))
    assert "_none_" in text
    assert "done (0)" in text


def test_done_cards_appear_with_their_count() -> None:
    """The specific complaint: finished work was invisible. It is a real column with a real count."""
    text = render_board(a_board(ready=1, done=3))
    assert "done (3)" in text


def test_the_heading_counts_match_the_total() -> None:
    text = render_board(a_board(ready=2, claimed=1, done=4))
    assert "ready (2)" in text and "claimed (1)" in text and "done (4)" in text
    assert "7 task(s)" in text


def test_an_entirely_empty_board_still_shows_its_shape() -> None:
    """Even with nothing at all, the columns tell a newcomer what states exist."""
    text = render_board(a_board())
    assert "0 task(s)" in text
    assert text.count("_none_") == len(STATUSES)
