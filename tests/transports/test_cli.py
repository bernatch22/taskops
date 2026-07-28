"""The CLI's parser, without running a command.

`build_parser` is the whole surface of the terminal: what names exist, and what flags each
one takes. Asserting on it is cheap and catches the two things a rename gets wrong — an old
name that stopped working, and an alias whose flags quietly drifted from the real command.
"""

from __future__ import annotations

from taskops.transports.cli.commands import ui
from taskops.transports.cli.main import build_parser


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
