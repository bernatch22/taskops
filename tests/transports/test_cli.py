"""The CLI's parser, without running a command.

`build_parser` is the whole surface of the terminal: what names exist, and what flags each
one takes. Asserting on it is cheap and catches the two things a rename gets wrong — an old
name that stopped working, and an alias whose flags quietly drifted from the real command.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskops.transports.cli.commands import ask, ui
from taskops.transports.cli.main import build_parser, main


def flags_of(name: str) -> set[str]:
    """Every option string the parser for `name` accepts, as a set."""
    parsed = build_parser().parse_args([name])
    return set(vars(parsed)) - {"command", "run", "deprecated_name"}


def test_the_ui_command_is_called_ui() -> None:
    parsed = build_parser().parse_args(["ui"])
    assert parsed.run is ui.run
    assert parsed.deprecated_name is False
    assert parsed.port == ui.DEFAULT_PORT


def test_the_old_studio_name_still_runs_and_marks_itself_deprecated() -> None:
    """A rename that breaks a line in somebody's shell history buys nothing. The alias reaches
    the same `run`; the flag is what makes `run` print the one deprecation line."""
    parsed = build_parser().parse_args(["studio"])
    assert parsed.run is ui.run
    assert parsed.deprecated_name is True


def test_the_alias_takes_exactly_the_flags_the_real_command_takes() -> None:
    """An alias that dropped `--readonly` would be worse than no alias: the board on the wall
    would start accepting writes, and nothing would say so."""
    assert flags_of("studio") == flags_of("ui")


def test_the_deprecated_name_is_hidden_from_help() -> None:
    """It is a bridge for existing muscle memory, not a second documented way in."""
    assert "studio" not in build_parser().format_help()


def test_the_help_lists_what_a_person_does_and_nothing_else() -> None:
    """The regroup, asserted where it is visible. `guard` and `brief` are typed by a git
    hook and by nothing else, so a person scanning this page for their task list should
    never have to decide whether one of them is what they wanted."""
    listed = _listed_commands()
    assert listed == {"init", "ui", "tasks", "run", "report", "recover", "sync"}


def _listed_commands() -> set[str]:
    """The command NAMES `--help` offers. Parsed out of the listing rather than searched
    for as substrings, because `init`'s own help text ends in "install the git hooks" — a
    naive `"hook" not in help` passes today and fails on a sentence nobody thought about."""
    listing = build_parser().format_help()
    body = listing.split("<command>\n", 1)[1].split("\noptions:", 1)[0]
    return {line.split()[0] for line in body.splitlines() if line.startswith("    ")}


@pytest.mark.parametrize("argv", [["next"], ["update", "tk-0"], ["ask", "tk-0"],
                                  ["plan", "-"], ["guard", "commit"], ["brief"], ["inbox"],
                                  ["track"], ["checkout"], ["ingest", "commit"],
                                  ["log", "tk-0"], ["hook", "stop"], ["dispatch"]])
def test_a_hidden_command_still_parses_and_still_runs(argv: list[str]) -> None:
    """Hidden, never removed: every one of these is already written into a hook line or a
    script somewhere, and the help page was what was failing — not the commands."""
    parsed = build_parser().parse_args(argv)
    assert callable(parsed.run)
    assert argv[0] not in _listed_commands()


def test_tasks_show_and_search_reach_the_same_run_the_old_verb_did() -> None:
    """Not an approximation of `ask` — the same function. Two implementations of "read a
    task" is how the CLI and the MCP start disagreeing about what a task looks like."""
    assert build_parser().parse_args(["tasks", "show", "tk-0"]).run is ask.run
    assert build_parser().parse_args(["tasks", "search", "whatever"]).run is ask.run


def test_the_group_takes_repo_before_or_after_the_subcommand(root: Path) -> None:
    """argparse writes a subparser's defaults over what the parent already parsed, so this
    is the assertion that `--repo` in front of the subcommand is not silently reset to `.`."""
    for argv in (["tasks", "--repo", str(root), "list"], ["tasks", "list", "--repo", str(root)]):
        assert main(argv) == 0


def test_tasks_add_creates_a_card_and_prints_its_id(root: Path,
                                                    capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["tasks", "add", "Write the thing", "--repo", str(root),
                 "--spec", "what done looks like", "--priority", "0"]) == 0
    created = capsys.readouterr().out
    assert "tk-" in created
    assert main(["tasks", "list", "--repo", str(root)]) == 0
    assert "Write the thing" in capsys.readouterr().out


def test_tasks_done_refuses_a_card_with_no_commit(root: Path,
                                                  capsys: pytest.CaptureFixture[str]) -> None:
    """The same guard `update --status done` enforces, because it IS that code path. A
    second door onto `done` that skipped the check is the whole reason for wrapping."""
    main(["tasks", "add", "Write the thing", "--repo", str(root)])
    task = "tk-" + capsys.readouterr().out.split("tk-")[1].split()[0]
    main(["next", "--repo", str(root), "--task", task, "--actor", "dev:berna"])
    capsys.readouterr()
    assert main(["tasks", "done", task, "--repo", str(root), "-m", "finished",
                 "--actor", "dev:berna"]) == 1
    assert "commit" in capsys.readouterr().err
