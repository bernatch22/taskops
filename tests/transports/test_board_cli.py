"""The three commands that start a board with no GitHub anywhere near it.

    taskops remote add <server>
    taskops board create <name>
    taskops board invite <who>

Every test here is a bug that was in the code and was found by TYPING those three lines, not by
reading them — which is the point of writing them down: each one passed the whole suite, because
every existing test of this surface reached `create_hosted` directly and none of them went
through the parser, the `--repo` default or the credential-less first command.

The end-to-end walk lives in `tests/e2e/`. These are the seams underneath it, one per line, so
that when one breaks the failure names the line rather than the flow.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskops._errors import BadRequest
from taskops.transports.cli.commands._board_render import plan_of
from taskops.transports.cli.commands._board_where import signed_in
from taskops.transports.cli.main import build_parser

SERVER = "https://boards.example.com"


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A scratch `TASKOPS_HOME`, always. A test that wrote the developer's own sessions file
    would sign this machine in to a server that does not exist."""
    monkeypatch.setenv("TASKOPS_HOME", str(tmp_path / "home"))


def parse(*argv: str):
    return build_parser().parse_args(argv)


# ---- `taskops board create <name>`


def test_the_name_is_positional_because_that_is_what_people_type() -> None:
    """`gh repo create <name>` is the shape this is copied from, and it was copied without the
    argument: the positional landed in `who`, which only `invite` reads, so `board create test`
    silently created a board named after the directory."""
    args = parse("board", "create", "test")

    assert args.verb == "create" and args.who == "test"
    assert plan_of(Path("."), SERVER, "", args.name or args.who, "", "")["name"] == "test"


def test_the_flag_still_wins_over_the_positional() -> None:
    """`--name` was the documented way before the positional existed, so it keeps meaning what
    it said — otherwise this change would break the only form the docs had."""
    args = parse("board", "create", "test", "--name", "otro")

    assert plan_of(Path("."), SERVER, "", args.name or args.who, "", "")["name"] == "otro"


def test_no_github_is_a_board_and_not_a_refusal() -> None:
    """THE refusal this whole path existed behind, and the first thing anybody hit: a checkout
    with no origin met "pass --github owner/repo" at the very first command, for a server that
    never needed GitHub to hold a board."""
    plan = plan_of(Path("."), SERVER, "", "", "", "")

    assert plan["github"] == "" and plan["name"]


def test_the_default_name_survives_the_default_repo(tmp_path: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    """`--repo` defaults to `.`, and `Path(".").name` is the EMPTY STRING — so the fallback
    refused with "cannot make a board name out of ``" about a directory with a perfectly good
    name. Asserted through the literal `Path(".")` the command actually passes."""
    here = tmp_path / "mi-proyecto"
    here.mkdir()
    monkeypatch.chdir(here)

    assert plan_of(Path("."), SERVER, "", "", "", "")["name"] == "mi-proyecto"


def test_a_name_that_cannot_be_one_is_still_refused(tmp_path: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    """The fallback got laxer, not absent: a directory of punctuation yields nothing usable and
    must say so, because the name is a URL segment."""
    here = tmp_path / "..."
    here.mkdir()
    monkeypatch.chdir(here)

    with pytest.raises(BadRequest, match="pass one with `--name`"):
        plan_of(Path("."), SERVER, "", "", "", "")


# ---- `taskops remote add <server>`, the command BEFORE there is a board


def test_a_bare_server_is_noted_rather_than_refused() -> None:
    """The first of the three lines, and it failed: `add_remote` is about a BOARD and demands
    the credential that writes to it, so a bare server URL — which names no board yet — was met
    with "pass --token, or run taskops login"."""
    from taskops.transports.cli.commands.remote import run_add

    said = run_add(parse("remote", "add", SERVER))

    assert "noted" in said and "taskops board create" in said


def test_a_board_url_still_takes_the_credential_path(tmp_path: Path) -> None:
    """The branch must be on the SHAPE and nothing else: a URL with a board on it is the old
    command, unchanged, and must still refuse when there is nothing to authenticate with."""
    from taskops.transports.cli.commands.remote import run_add
    from taskops.usecases import init

    init(tmp_path, install_git_hooks=False)

    with pytest.raises(BadRequest, match="no token and no session"):
        run_add(parse("remote", "add", f"{SERVER}/axion", "--repo", str(tmp_path)))


def test_a_noted_server_is_not_a_login() -> None:
    """It is recorded in the sessions file with an EMPTY session, so every reader has to treat
    that as absent. One did not, and sent an empty bearer — turning "you are not signed in"
    into a bare 401 from the server."""
    from taskops.transports.cli.commands.remote import run_add

    run_add(parse("remote", "add", SERVER))

    with pytest.raises(BadRequest, match="not signed in"):
        signed_in(SERVER, "")
