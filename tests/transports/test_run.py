"""`taskops run` — the one command in this package that spends money.

Nothing here starts a real Claude Code: the launch is monkeypatched, because a suite that
spawned workers would bill whoever ran it. What IS pinned is the part the rename was for —
that the price is stated before anything starts, and that saying no leaves the board alone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from taskops.transports.cli.main import build_parser, main
from taskops.usecases import ask, init, plan


@pytest.fixture
def project(tmp_path: Path) -> Path:
    init(tmp_path, install_git_hooks=False)
    plan(tmp_path, [{"title": "A", "spec": "a"}, {"title": "B", "spec": "b"}], actor="dev:berna")
    return tmp_path


@pytest.fixture
def spawns(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record what WOULD have been launched, and start no process."""
    import importlib

    from taskops.engine.worker import Launched, prepare

    # The MODULE, by name: `taskops.usecases.dispatch` as an ATTRIBUTE is the function the
    # package re-exports under the same name, and patching that patches nothing.
    module = importlib.import_module("taskops.usecases.dispatch")

    started: list[str] = []

    def fake_launch(root: Path, task: Any, *, actor: str, **_: Any) -> Launched:
        started.append(task["id"])
        ready = prepare(root, task, actor=actor)
        return Launched(actor=actor, task=task["id"], pid=4242, tree=ready.tree,
                        log=ready.log, branch=ready.branch, brief=ready.brief)

    monkeypatch.setattr(module, "launch", fake_launch)
    return started


def answer(monkeypatch: pytest.MonkeyPatch, said: str) -> None:
    monkeypatch.setattr("builtins.input", lambda *_: said)


def test_run_is_listed_next_to_the_other_person_commands() -> None:
    """The point of the rename. As `dispatch --spawn` the billed path was a flag on a hidden
    command: the most expensive thing here was the hardest one to find."""
    listing = build_parser().format_help()
    assert "\n    run " in listing
    assert "experimental" in listing


def test_a_dry_run_previews_and_never_asks(project: Path, spawns: list[str],
                                           capsys: pytest.CaptureFixture[str]) -> None:
    """Looking has to stay free, and free means it does not even prompt — a confirmation on a
    preview is how people learn to answer prompts without reading them."""
    code = main(["run", "--repo", str(project), "--count", "2", "--dry-run",
                 "--actor", "dev:berna"])
    assert code == 0
    out = capsys.readouterr()
    assert "NOTHING STARTED" in out.out
    assert spawns == [], "a dry run started a worker"


def test_confirming_spawns_and_warns_about_the_bill_first(project: Path, spawns: list[str],
                                                          monkeypatch: pytest.MonkeyPatch,
                                                          capsys: pytest.CaptureFixture[str]
                                                          ) -> None:
    """The warning is the whole feature: a person who types this must read what it costs and
    what the free alternative is BEFORE the first session opens."""
    answer(monkeypatch, "y")
    assert main(["run", "--repo", str(project), "--count", "1", "--actor", "dev:berna"]) == 0
    out = capsys.readouterr()
    assert "NEW billed Claude session" in out.err
    assert "taskops_dispatch" in out.err, "the warning must name the free way to parallelise"
    assert len(spawns) == 1


def test_yes_skips_the_prompt_for_an_unattended_caller(project: Path, spawns: list[str],
                                                       monkeypatch: pytest.MonkeyPatch,
                                                       capsys: pytest.CaptureFixture[str]
                                                       ) -> None:
    """A fleet script cannot answer a prompt, and a command that hangs forever waiting is a
    worse failure than one that spends money on purpose."""
    monkeypatch.setattr("builtins.input", _refuse_to_be_called)
    assert main(["run", "--repo", str(project), "--count", "1", "--yes",
                 "--actor", "dev:berna"]) == 0
    assert "NEW billed Claude session" in capsys.readouterr().err, "--yes silenced the warning"
    assert len(spawns) == 1


def _refuse_to_be_called(*_: object) -> str:
    raise AssertionError("--yes still asked")


def test_refusing_aborts_and_assigns_nothing(project: Path, spawns: list[str],
                                             monkeypatch: pytest.MonkeyPatch,
                                             capsys: pytest.CaptureFixture[str]) -> None:
    """Saying no must cost nothing at all — not a process, and not an assignment that would
    leave the cards invisible to every other agent afterwards."""
    answer(monkeypatch, "")
    assert main(["run", "--repo", str(project), "--actor", "dev:berna"]) == 0
    assert "aborted" in capsys.readouterr().out
    assert spawns == []
    for card in _cards(project):
        assert ask(project, card)["task"]["assignee"] == "", "a refused run assigned a card"


def test_no_stdin_counts_as_no(project: Path, spawns: list[str],
                               monkeypatch: pytest.MonkeyPatch) -> None:
    """A hook or a CI job has no tty. Reading that as agreement is how the bill arrives from
    a machine nobody was watching."""
    monkeypatch.setattr("builtins.input", _raise_eof)
    assert main(["run", "--repo", str(project), "--actor", "dev:berna"]) == 0
    assert spawns == []


def _raise_eof(*_: object) -> str:
    raise EOFError


def _cards(project: Path) -> list[str]:
    from taskops.usecases import board

    return [card["task"]["id"] for column in board(project)["columns"]
            for card in column["cards"]]


def test_the_old_dispatch_still_takes_spawn_and_still_runs(project: Path,
                                                           spawns: list[str]) -> None:
    """Hidden, never removed: `dispatch --spawn` is written into scripts that already exist,
    so it keeps working — with its help text pointing at the new name."""
    assert main(["dispatch", "--repo", str(project), "--count", "1", "--spawn",
                 "--actor", "dev:berna"]) == 0
    assert len(spawns) == 1
    assert "dispatch" not in build_parser().format_help().split("options:")[0]


def test_run_takes_the_same_flags_dispatch_does() -> None:
    """One parser, two names. A `run` that had quietly lost `--prefix` would send a fleet out
    under the wrong actor ids and nothing would say so."""
    shared = {"repo", "tasks", "count", "prefix", "model", "dry_run", "actor"}
    for name in ("run", "dispatch"):
        assert shared <= set(vars(build_parser().parse_args([name])))
