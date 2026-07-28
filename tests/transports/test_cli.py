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
from taskops.usecases import next_task


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
    assert listed == {"init", "ui", "serve", "tasks", "run", "report", "recover", "sync",
                      "remote", "push", "pull"}


def test_the_remote_verbs_are_the_developers_and_are_listed() -> None:
    """`remote`, `push` and `pull` decide when THIS MACHINE talks to a server, which is a
    person's call and not an agent's — so they are on the CLI, in the help, and deliberately
    absent from the MCP tool surface. They sit beside `sync` rather than replacing it: a team
    with no server still converges through git, and that path is not deprecated."""
    for verb in ("remote", "push", "pull"):
        assert "repo" in flags_of(verb), f"{verb} cannot be pointed at a project"


@pytest.mark.parametrize("gone", ["guard", "hook", "ingest", "brief", "inbox", "track",
                                  "checkout", "next", "update", "ask", "plan", "dispatch",
                                  "log"])
def test_the_thirteen_hidden_commands_are_gone_not_hidden(gone: str) -> None:
    """Seven listed AND seven existing. Hidden reads the same from the outside as absent and
    is not the same thing: every one of these was still a door into the developer's binary,
    which is how git and Claude Code kept entering through it. `guard`/`hook`/`ingest` and the
    session verbs live in `taskops.transports.hooks`; the rest are the agent's, over MCP."""
    with pytest.raises(SystemExit):
        build_parser().parse_args([gone])


def _listed_commands() -> set[str]:
    """The command NAMES `--help` offers. Parsed out of the listing rather than searched
    for as substrings, because `init`'s own help text ends in "install the git hooks" — a
    naive `"hook" not in help` passes today and fails on a sentence nobody thought about."""
    listing = build_parser().format_help()
    body = listing.split("<command>\n", 1)[1].split("\noptions:", 1)[0]
    # Exactly four spaces then a word: a help string long enough to wrap continues on a line
    # indented FOURTEEN, and counting those made the first word of a description a "command"
    # — which is how adding `serve` reported a phantom command called `token`.
    return {line.split()[0] for line in body.splitlines()
            if line.startswith("    ") and not line.startswith("     ")}


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
    next_task(root, task=task, actor="dev:berna")
    capsys.readouterr()
    assert main(["tasks", "done", task, "--repo", str(root), "-m", "finished",
                 "--actor", "dev:berna"]) == 1
    assert "commit" in capsys.readouterr().err


def test_tasks_edit_rewrites_the_card_from_the_terminal(
        root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The whole door, end to end: flags in, a rewritten row out, and the list showing it."""
    main(["tasks", "add", "Write the thing", "--repo", str(root), "--spec", "wrong brief"])
    task = "tk-" + capsys.readouterr().out.split("tk-")[1].split()[0]

    assert main(["tasks", "edit", task, "--repo", str(root), "--title", "Write the RIGHT thing",
                 "--spec", "the real brief", "--priority", "0"]) == 0
    assert "edited title, spec, priority" in capsys.readouterr().out
    assert main(["tasks", "show", task, "--repo", str(root)]) == 0
    assert "the real brief" in capsys.readouterr().out


def test_tasks_edit_with_no_flags_says_so_instead_of_pretending(
        root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """At least one field is required, and the refusal comes from the use case — so the MCP
    and HTTP surfaces would refuse identically rather than only argparse knowing the rule."""
    main(["tasks", "add", "Write the thing", "--repo", str(root)])
    task = "tk-" + capsys.readouterr().out.split("tk-")[1].split()[0]

    assert main(["tasks", "edit", task, "--repo", str(root)]) == 1
    assert "nothing to edit" in capsys.readouterr().err
