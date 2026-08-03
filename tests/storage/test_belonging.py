"""Which chapter a CARD is in — including the one that names none.

The model's first sentence is that every card belongs to exactly one milestone, and `plan` refuses
to create one without. What was left over was history: a board that existed before 0.5.0 has cards
carrying `""` for ever, and the code carried a permanent bucket to draw them in — the sentence being
false on every board that predates the model.

These tests pin the line between resolving and inventing, which is the whole of it: with ONE chapter
in the board's life there is nothing to guess, and with several there is.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from taskops.contracts import Task
from taskops.engine import record, replay
from taskops.storage import Store
from taskops.storage.belonging import chapter_of, sole
from taskops.usecases import init
from taskops.usecases.milestone import open_chapter


@pytest.fixture()
def board(tmp_path: Path) -> Iterator[Path]:
    init(tmp_path)
    yield tmp_path


def legacy_card(root: Path, task_id: str) -> Task:
    """A `created` event with no `milestone` in its body — the shape a pre-0.5.0 log holds. It
    cannot be made through `plan`, which refuses a board with no chapter."""
    with Store(root) as store:
        made = record(store, task=task_id, actor="dev:berna", kind="created",
                      body={"title": "antes de los capitulos", "spec": "s"})
        replay.apply(store, [made])
        return store.tasks.need(task_id)


def test_a_legacy_card_lands_in_the_board_s_only_chapter(board: Path) -> None:
    """One chapter in the board's whole life means there is no choice to make. Every clone folds
    the same log to the same id, so nothing about the past is invented by saying so."""
    card = legacy_card(board, "tk-legacy")
    assert card["milestone"] == "", "the row itself still says what the event said"
    chapter = open_chapter(board, "El importador", actor="dev:berna")

    with Store(board) as store:
        assert sole(store) == chapter["id"]
        assert chapter_of(card, sole(store)) == chapter["id"]


def test_with_SEVERAL_chapters_a_legacy_card_stays_loose(board: Path) -> None:
    """Here guessing IS inventing: two candidates and a record that cannot say which. So the card
    stays loose and every surface says so — the honest answer, and the reason the bucket still
    exists in the code rather than being deleted."""
    card = legacy_card(board, "tk-legacy")
    open_chapter(board, "El importador", actor="dev:berna")
    open_chapter(board, "La facturacion", actor="dev:berna")

    with Store(board) as store:
        assert sole(store) == ""
        assert chapter_of(card, sole(store)) == ""


def test_a_closed_chapter_still_counts_as_the_only_one(board: Path) -> None:
    """`sole` reads every chapter the board ever had, not the active ones. A board whose single
    chapter was reached has still only ever had one, and its history belongs to it — resolving
    against `active` would drop the cards back into a bucket the day somebody closed it."""
    from taskops.usecases.milestone import verify

    card = legacy_card(board, "tk-legacy")
    chapter = open_chapter(board, "El importador", actor="dev:berna")
    verify(board, chapter["id"], actor="dev:berna")

    with Store(board) as store:
        assert chapter_of(card, sole(store)) == chapter["id"]


def test_a_card_that_NAMES_a_chapter_is_never_moved_by_the_fold(board: Path) -> None:
    """The resolution is for the cards that name none. A card planned into a chapter keeps it
    whatever else the board has — otherwise a second chapter would silently re-home the first
    chapter's work."""
    first = open_chapter(board, "El importador", actor="dev:berna")
    named: Task = {**legacy_card(board, "tk-named"), "milestone": first["id"]}

    with Store(board) as store:
        assert chapter_of(named, sole(store)) == first["id"]


def test_the_COUNTS_have_no_bucket_when_the_answer_is_determined(board: Path) -> None:
    """The end of it, at the surface a person actually sees: a board with one chapter and legacy
    cards drew `La imprenta 0/6` beside `No milestone 56` — its own chapter next to a bucket holding
    everything it had ever finished. There is no `""` key to draw any more."""
    from taskops.usecases._contextviews import chapters

    legacy_card(board, "tk-one")
    legacy_card(board, "tk-two")
    chapter = open_chapter(board, "El importador", actor="dev:berna")

    with Store(board) as store:
        counts = chapters(store).counts

    assert "" not in counts, counts
    assert counts[chapter["id"]]["total"] == 2


def test_the_bucket_comes_BACK_when_a_second_chapter_makes_it_ambiguous(board: Path) -> None:
    """The other direction, and the one a hurried fix breaks: the bucket is not dead code, it is
    the answer when the record cannot settle the question."""
    from taskops.usecases._contextviews import chapters

    legacy_card(board, "tk-one")
    open_chapter(board, "El importador", actor="dev:berna")
    open_chapter(board, "La facturacion", actor="dev:berna")

    with Store(board) as store:
        assert chapters(store).counts[""]["total"] == 1
