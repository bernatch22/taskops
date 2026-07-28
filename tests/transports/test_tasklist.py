"""`taskops tasks` — what the list shows when the project is finished.

The bug this pins was reported from a real repository: six cards, all of them done, and the
command printed `no open tasks (6 in total)` and nothing else. That is the same mistake the
board fixed by never hiding a column — a reader who cannot see the finished work cannot tell
whether the tool lost it or whether the project is over.

Driven through `main`, not through the renderer, because the flags are half the fix: a
renderer that can list closed cards and a CLI with no way to ask is not a fix at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskops.transports.cli.main import main
from taskops.usecases import update


def a_closed_card(root: Path, title: str, capsys: pytest.CaptureFixture[str]) -> str:
    """One card, created and then cancelled.

    `cancelled` rather than `done` because closing as done requires a commit bound to the
    card, and this suite has no git repository — both are closed statuses to every reader
    of the list, which is the property under test.
    """
    main(["tasks", "add", title, "--repo", str(root)])
    task = "tk-" + capsys.readouterr().out.split("tk-")[1].split()[0]
    update(root, task, actor="dev:berna", status="cancelled")
    capsys.readouterr()
    return task


def test_a_project_with_only_closed_cards_lists_them(
        root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """THE bug. Nothing open is an answer, but it is not the whole answer."""
    a_closed_card(root, "Ship the thing", capsys)
    assert main(["tasks", "--repo", str(root)]) == 0
    text = capsys.readouterr().out
    assert "Ship the thing" in text
    assert "nothing open" in text
    assert "1 closed" in text


def test_open_cards_still_come_first_and_alone(
        root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The default is unchanged while anything is open: closed cards accumulate forever and
    would push the answer to "what do I do next" off the screen."""
    a_closed_card(root, "Old finished work", capsys)
    main(["tasks", "add", "Live work", "--repo", str(root)])
    capsys.readouterr()

    assert main(["tasks", "--repo", str(root)]) == 0
    text = capsys.readouterr().out
    assert "Live work" in text
    assert "Old finished work" not in text
    assert "1 open" in text and "closed" not in text


def test_all_shows_both_groups(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    a_closed_card(root, "Old finished work", capsys)
    main(["tasks", "add", "Live work", "--repo", str(root)])
    capsys.readouterr()

    assert main(["tasks", "--repo", str(root), "--all"]) == 0
    text = capsys.readouterr().out
    assert "## open" in text and "## closed" in text
    assert "Live work" in text and "Old finished work" in text
    assert "1 open, 1 ready, 1 closed" in text


def test_status_filters_to_one_status(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    a_closed_card(root, "Old finished work", capsys)
    main(["tasks", "add", "Live work", "--repo", str(root)])
    capsys.readouterr()

    assert main(["tasks", "list", "--repo", str(root), "--status", "cancelled"]) == 0
    text = capsys.readouterr().out
    assert "Old finished work" in text
    assert "Live work" not in text


def test_a_status_with_no_cards_says_so_rather_than_printing_nothing(
        root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    a_closed_card(root, "Old finished work", capsys)
    assert main(["tasks", "--repo", str(root), "--status", "review"]) == 0
    assert "no review tasks (1 in total)" in capsys.readouterr().out


def test_an_invalid_status_is_refused_by_name(
        root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The package's own refusal, not argparse's usage dump: the rejected word, then the
    legal ones, on one line a reader can act on."""
    assert main(["tasks", "--repo", str(root), "--status", "finito"]) == 1
    err = capsys.readouterr().err
    assert "`finito` is not a status" in err
    assert "in_progress" in err and "cancelled" in err
