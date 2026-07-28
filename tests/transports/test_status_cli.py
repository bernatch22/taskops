"""`taskops status --prompt` end to end, where the guarantees actually have to hold.

The renderer is pure and tested from dicts; what is left to prove is the part only the
command can get wrong — that a broken, missing or foreign directory produces NO output and
exit 0, and that the whole path is fast enough to sit in front of every shell line.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from taskops.storage import PROJECT_DIR
from taskops.transports.cli.main import main

BUDGET = 2.0
"""Seconds allowed for the in-process call. The real target is 50ms and a warm run is far
under it; the ceiling is this generous because CI disks are not laptops and a timing test
that flakes gets deleted, which would leave the budget unguarded entirely. What it catches
is the regression that matters — somebody putting a network call or a model behind it."""


def prompt(repo: Path, *extra: str) -> int:
    return main(["status", "--prompt", "--repo", str(repo), *extra])


def test_a_directory_that_is_not_a_project_prints_nothing_and_exits_zero(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The failure mode this whole command is shaped around: a prompt segment that
    printed `taskops: not a taskops project` would put that line above EVERY command
    typed in every other directory on the machine."""
    assert prompt(tmp_path) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_a_corrupt_database_prints_nothing_and_exits_zero(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Not "not a project" — a real one whose db is garbage, which is what a half-written
    file or a lock held by another agent looks like from here."""
    (tmp_path / PROJECT_DIR).mkdir()
    (tmp_path / PROJECT_DIR / "taskops.db").write_bytes(b"this is not a sqlite file")
    assert prompt(tmp_path) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_an_empty_project_prints_nothing_and_exits_zero(
        root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert prompt(root) == 0
    assert capsys.readouterr().out == ""


def test_a_project_with_a_card_prints_one_line(
        root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from taskops.usecases import plan

    plan(root, [{"title": "write the thing"}], actor="dev:berna")
    assert prompt(root) == 0
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    assert out.startswith(f"tk:{root.name} 1")


def test_porcelain_answers_where_prompt_stays_silent(
        root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """An empty project has nothing to SAY in a prompt but plenty to REPORT: a script
    asking for counts wants the zeros, not a blank."""
    assert main(["status", "--porcelain", "--repo", str(root)]) == 0
    pairs = dict(line.split("=", 1) for line in capsys.readouterr().out.splitlines())
    assert pairs["version"] == "1"
    assert pairs["open"] == "0"
    assert pairs["prompt"] == ""


def test_porcelain_survives_a_directory_that_is_not_a_project(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["status", "--porcelain", "--repo", str(tmp_path)]) == 0
    assert capsys.readouterr().out == ""


def test_the_prompt_path_stays_inside_its_time_budget(
        root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Measured IN PROCESS on purpose. Starting CPython costs more than this command
    does, so a subprocess here would be a test of the interpreter — which is exactly why
    the zsh snippet in docs/prompt.md runs the whole thing asynchronously."""
    from taskops.usecases import plan

    plan(root, [{"title": f"card {n}"} for n in range(20)], actor="dev:berna")
    capsys.readouterr()
    started = time.perf_counter()
    assert prompt(root) == 0
    assert time.perf_counter() - started < BUDGET


def test_zsh_colour_is_opt_in(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from taskops.usecases import plan

    plan(root, [{"title": "one"}], actor="dev:berna")
    assert prompt(root, "--colour", "zsh") == 0
    assert "%F{blue}" in capsys.readouterr().out
