"""`taskops open` — the URL it builds, and the four ways it can have nothing to build.

The whole value of the command is that nobody assembles the address by hand, so the assertions
are about assembly: the right host, the right project, and a credential taken from whichever of
the two places is holding a live one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskops._errors import NotInitialized
from taskops.usecases import add_remote, board_url, root_url
from taskops.usecases._sessionfile import save_session

SERVER = "https://boards.example.com"


@pytest.fixture(autouse=True)
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Nobody's real `~/.taskops/sessions.json` takes part in a test run."""
    monkeypatch.setenv("TASKOPS_HOME", str(tmp_path))


def test_the_board_url_carries_the_projects_own_token(root: Path) -> None:
    """The machine credential opens exactly this board and is what the project was configured
    with, so it wins over a session that happens to be lying around."""
    save_session(SERVER, "ts_person", "bernatch22")
    add_remote(root, f"{SERVER}/axion", token="tk_machine")
    assert board_url(root) == f"{SERVER}/axion/?token=tk_machine"


def test_a_project_with_no_remote_says_what_to_run(root: Path) -> None:
    """Not a traceback and not a guess at a hostname: the two commands that would work."""
    with pytest.raises(NotInitialized) as raised:
        board_url(root)
    assert "remote add" in str(raised.value)
    assert "taskops ui" in str(raised.value)


def test_a_session_backed_project_follows_the_stored_session(root: Path) -> None:
    """`remote add` with no token stores the session of the day. When a later `login` mints a
    new one, the home directory is the only copy that gets refreshed — so it is the one that
    must be used, or every checkout opens with a session that expired on Sunday."""
    add_remote(root, f"{SERVER}/axion", token="session:ts_stale")
    save_session(SERVER, "ts_fresh", "bernatch22")
    assert board_url(root) == f"{SERVER}/axion/?token=ts_fresh"


def test_the_local_session_prefix_never_reaches_the_wire(root: Path) -> None:
    """`session:` is a marker for `push`'s error messages; the server has never heard of it."""
    save_session(SERVER, "ts_fresh", "bernatch22")
    add_remote(root, f"{SERVER}/axion", token="session:ts_fresh")
    assert "session%3A" not in board_url(root)
    assert "?token=ts_fresh" in board_url(root)


def test_the_root_is_the_one_server_this_machine_knows() -> None:
    save_session(SERVER, "ts_person", "bernatch22")
    url, found = root_url()
    assert url == f"{SERVER}/?token=ts_person"
    assert found["login"] == "bernatch22"


def test_two_servers_refuse_to_be_guessed_between() -> None:
    """Opening another team's board is worse than one more word on the command line."""
    save_session("https://a.example.com", "ts_a", "bernatch22")
    save_session("https://b.example.com", "ts_b", "someone")
    with pytest.raises(NotInitialized) as raised:
        root_url()
    assert "--server" in str(raised.value)
    assert root_url("https://b.example.com")[0].endswith("?token=ts_b")


def test_a_server_never_signed_in_to_names_the_login_command() -> None:
    with pytest.raises(NotInitialized) as raised:
        root_url(SERVER)
    assert f"taskops login {SERVER}" in str(raised.value)


def test_signed_in_nowhere_says_so_rather_than_opening_nothing() -> None:
    with pytest.raises(NotInitialized) as raised:
        root_url()
    assert "not signed in anywhere" in str(raised.value)
