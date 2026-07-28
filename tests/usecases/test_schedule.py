"""The sweep's triggers: the scheduled-task file, and the once-a-day guard.

No test here may run a real sweep — a sweep calls the model, and a test suite that spends
money is a test suite people stop running. The spawn is patched everywhere it appears.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from taskops._errors import BadRequest
from taskops.usecases import init
from taskops.usecases.schedule import (
    STAMP,
    claude_home,
    install_schedule,
    mark_swept,
    read_schedule,
    sweep_due,
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    init(tmp_path / "repo", install_git_hooks=False)
    return tmp_path / "repo"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: Any) -> Path:
    """A fake `$CLAUDE_CONFIG_DIR`. Honouring it is the mechanism, not scaffolding: people who
    moved their Claude config did so on purpose."""
    where = tmp_path / "claude"
    where.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(where))
    return where


def test_the_config_dir_env_var_wins_over_the_home_directory(home: Path) -> None:
    assert claude_home() == home


def test_install_writes_the_skill_where_claude_reads_scheduled_tasks(project: Path,
                                                                    home: Path) -> None:
    found = install_schedule(project)
    path = home / "scheduled-tasks" / "taskops-sweep" / "SKILL.md"
    assert path.is_file() and found["path"] == str(path)
    assert found["body"].startswith("---\nname: taskops-sweep\n")
    assert "description:" in found["body"].split("---")[1]


@pytest.mark.usefixtures("home")
def test_install_hands_back_the_sentence_that_sets_the_schedule(project: Path) -> None:
    """The half we cannot do. The command must carry it, or somebody believes a report is
    being written every night when nothing is scheduled at all."""
    found = install_schedule(project)
    assert "/taskops:sweep" in found["ask"] and str(project) in found["ask"]
    assert "scheduled task" in found["ask"]


def test_install_refuses_when_claude_code_is_not_installed(project: Path,
                                                           tmp_path: Path,
                                                           monkeypatch: Any) -> None:
    """It must NOT mkdir a config directory for an app that is not here — that directory
    would never be read, and the command would report success for a task that cannot run."""
    absent = tmp_path / "nope" / ".claude"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(absent))
    with pytest.raises(BadRequest, match="Claude Code was not found"):
        install_schedule(project)
    assert not absent.exists()


@pytest.mark.usefixtures("home")
def test_status_reports_a_missing_file_as_an_answer(project: Path) -> None:
    found = read_schedule(project)
    assert found["exists"] is False and found["body"] == ""


@pytest.mark.usefixtures("home")
def test_status_reads_back_what_install_wrote(project: Path) -> None:
    written = install_schedule(project)
    assert read_schedule(project)["body"] == written["body"]


def test_a_project_that_was_never_swept_is_due(project: Path) -> None:
    assert sweep_due(project) is True


def test_a_project_swept_today_is_not_due_again(project: Path) -> None:
    """Ten sessions resumed in one morning must cost ONE model call."""
    mark_swept(project)
    assert sweep_due(project) is False
    assert sweep_due(project) is False


def test_yesterdays_stamp_is_due_again(project: Path) -> None:
    (project / ".taskops" / STAMP).write_text("2020-01-01", encoding="utf-8")
    assert sweep_due(project) is True


def test_an_unreadable_stamp_costs_a_sweep_and_never_loses_one(project: Path) -> None:
    """A corrupt stamp must fail towards "run it" — the sweep is idempotent, a lost report
    is not."""
    (project / ".taskops" / STAMP).write_text("garbage", encoding="utf-8")
    assert sweep_due(project) is True
