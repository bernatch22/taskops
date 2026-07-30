"""Signing in with GitHub, end to end, against a server written from the frozen contract.

Half of these are security assertions, and that is the right proportion for this feature: it
is the only place in taskops where a secret belonging to something ELSE (GitHub, and through
it every repository the person can reach) passes through our hands. The file mode, the
absence of the token from stdout, the session never being printed unasked — each of those
already went wrong somewhere in the industry, and each one is one line to check.

The rest is the teammate's three commands: `login`, `remote add` with no `--token`, `push`.
"""

from __future__ import annotations

import stat
from pathlib import Path
from typing import Iterator

import pytest

from taskops.transports.cli.commands import login as login_cli
from taskops.transports.cli.main import main
from taskops.usecases import add_remote, init, login, logout, plan, push, read_remote
from taskops.usecases._sessionfile import sessions_path
from tests.e2e.fakeserver import GITHUB_TOKEN, SESSION, TOKEN, Fake, running


@pytest.fixture
def fake() -> Fake:
    return Fake()


@pytest.fixture
def base(fake: Fake) -> Iterator[str]:
    yield from running(fake)


@pytest.fixture
def second(request: pytest.FixtureRequest) -> str:
    """A SECOND server, for the multi-server rules. The generator is held open through the
    test's finalizer — dropping it closes the socket, and the failure reads as a refused
    connection rather than as a test that tidied itself up too early."""
    alive = running(Fake())
    request.addfinalizer(alive.close)
    return next(alive)


@pytest.fixture(autouse=True)
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Never the developer's own `~/.taskops/sessions.json`. A test that logged in for real
    would overwrite a session somebody is using."""
    where = tmp_path / "home"
    monkeypatch.setenv("TASKOPS_HOME", str(where))
    return where


# ── the happy path ──────────────────────────────────────────────────────────────────────

def test_a_login_stores_the_session_and_lists_the_projects(base: str) -> None:
    done = login(base, GITHUB_TOKEN)
    assert done["login"] == "jp"
    assert done["projects"] == ["axion", "taskops"]


def test_the_session_file_is_readable_only_by_its_owner(base: str) -> None:
    """0600 at creation. The session is a bearer for every project on that server."""
    login(base, GITHUB_TOKEN)
    mode = stat.S_IMODE(sessions_path().stat().st_mode)
    assert mode == 0o600, f"sessions.json is {oct(mode)}"


def test_the_session_file_lives_in_the_home_not_in_a_repository(base: str, home: Path,
                                                                tmp_path: Path) -> None:
    """A file that never enters a work tree can never enter a commit — which is the failure
    the 0600 mode exists to make survivable and this one makes impossible."""
    init(tmp_path / "project", install_git_hooks=False)
    login(base, GITHUB_TOKEN)
    assert sessions_path() == home / ".taskops" / "sessions.json"
    assert not (tmp_path / "project" / ".taskops" / "sessions.json").exists()


def test_the_github_token_never_reaches_the_disk(base: str) -> None:
    """It crosses one HTTPS call and is gone. What is kept is the session, which is scoped to
    one server and expires by itself; the GitHub token is neither."""
    login(base, GITHUB_TOKEN)
    assert GITHUB_TOKEN not in sessions_path().read_text(encoding="utf-8")


def test_the_terminal_shows_the_login_and_never_the_secrets(base: str,
                                                            capsys: pytest.CaptureFixture[str],
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    """A terminal is a thing people screenshot. The GitHub token and the session are both
    absent; the reader gets their GitHub login and one paste-ready line per project."""
    monkeypatch.setattr(login_cli, "github_token", lambda: GITHUB_TOKEN)
    assert main(["login", base]) == 0
    shown = capsys.readouterr().out
    assert "jp" in shown
    assert f"taskops remote add {base}/axion" in shown
    assert GITHUB_TOKEN not in shown
    assert SESSION not in shown


def test_the_session_is_printed_only_when_explicitly_asked(base: str,
                                                           capsys: pytest.CaptureFixture[str],
                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    """The UI's unlock screen needs it pasted in, so there IS a way — an explicit one."""
    monkeypatch.setattr(login_cli, "github_token", lambda: GITHUB_TOKEN)
    main(["login", base])
    capsys.readouterr()
    assert main(["login", base, "--show"]) == 0
    assert SESSION in capsys.readouterr().out


# ── where the token comes from ──────────────────────────────────────────────────────────

def test_gh_auth_token_is_used_when_gh_is_there(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(login_cli, "_from_gh", lambda: GITHUB_TOKEN)
    monkeypatch.setattr(login_cli.getpass, "getpass",
                        lambda _prompt: pytest.fail("gh answered; nobody should be prompted"))
    assert login_cli.github_token() == GITHUB_TOKEN


def test_a_missing_gh_falls_back_to_a_hidden_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    """`getpass`, not `input`: a token typed into a visible prompt lands in the scrollback."""
    monkeypatch.setattr(login_cli, "_from_gh", lambda: "")
    monkeypatch.setattr(login_cli.getpass, "getpass", lambda _prompt: "  typed-by-hand  ")
    assert login_cli.github_token() == "  typed-by-hand  "


# ── refusals ────────────────────────────────────────────────────────────────────────────

def test_a_403_is_relayed_verbatim(base: str, fake: Fake) -> None:
    """The server's sentence knows WHY GitHub said no. Ours would not."""
    fake.github_ok = False
    with pytest.raises(Exception) as raised:
        login(base, GITHUB_TOKEN)
    assert "not on any repo this server serves" in str(raised.value)


def test_remote_add_without_a_token_or_a_session_names_both_ways_out(tmp_path: Path) -> None:
    init(tmp_path, install_git_hooks=False)
    with pytest.raises(Exception) as raised:
        add_remote(tmp_path, "https://taskops.example.com/axion")
    told = str(raised.value)
    assert "--token" in told
    assert "taskops login" in told


# ── the teammate's three commands ───────────────────────────────────────────────────────

def test_remote_add_with_no_token_uses_the_session_and_push_works(base: str, fake: Fake,
                                                                  tmp_path: Path) -> None:
    """THE end-to-end. Log in once, point a checkout at a project, push — no secret handled."""
    login(base, GITHUB_TOKEN)
    init(tmp_path, install_git_hooks=False)
    added = add_remote(tmp_path, f"{base}/axion")
    assert added["token"] == f"session:{SESSION}"
    plan(tmp_path, [{"title": "a card that has to cross the wire"}])
    assert push(tmp_path).accepted == 0, "the plan shared itself under the session credential"
    assert fake.posts == 1, "one POST: the plan's own"


def test_an_expired_session_says_to_log_in_again(base: str, fake: Fake, tmp_path: Path) -> None:
    """Seven days later the server answers 401. A bare 401 would leave the reader guessing at
    a network, a token, or a permission; the shape of the stored credential says which it is."""
    login(base, GITHUB_TOKEN)
    init(tmp_path, install_git_hooks=False)
    add_remote(tmp_path, f"{base}/axion")
    fake.session_valid = False
    with pytest.raises(Exception) as raised:
        push(tmp_path)
    told = str(raised.value)
    assert "expired" in told
    assert f"taskops login {base}" in told


def test_a_project_token_still_gets_the_plain_401(base: str, tmp_path: Path) -> None:
    """The other half of the same rule: a wrong TOKEN is not an expired session, and telling
    its owner to log in would send them down a road that does not lead anywhere."""
    init(tmp_path, install_git_hooks=False)
    add_remote(tmp_path, f"{base}/axion", "not-the-token")
    with pytest.raises(Exception) as raised:
        push(tmp_path)
    assert "expired" not in str(raised.value)


# ── several servers, and leaving ────────────────────────────────────────────────────────

def test_logging_in_to_a_second_server_does_not_disturb_the_first(base: str, second: str,
                                                                  tmp_path: Path) -> None:
    """One entry per URL. A developer with a work server and a personal one has both."""
    login(base, GITHUB_TOKEN)
    login(second, GITHUB_TOKEN)
    init(tmp_path, install_git_hooks=False)
    add_remote(tmp_path, f"{base}/axion")
    assert read_remote(tmp_path) is not None
    assert sorted(k for k in _stored()) == sorted([base, second])


def test_logout_forgets_only_that_server(base: str, second: str) -> None:
    login(base, GITHUB_TOKEN)
    login(second, GITHUB_TOKEN)
    assert logout(base) == base
    assert list(_stored()) == [second]


def test_logout_of_a_server_nobody_signed_in_to_says_so(base: str) -> None:
    with pytest.raises(Exception) as raised:
        logout(base)
    assert "not signed in" in str(raised.value)


def test_the_project_token_path_is_untouched(base: str, tmp_path: Path) -> None:
    """Sessions are an ADDITION. A team that issues tokens by hand keeps working exactly as
    before, and nothing about `remote add --token` changed."""
    init(tmp_path, install_git_hooks=False)
    add_remote(tmp_path, base, TOKEN)
    plan(tmp_path, [{"title": "still the old way"}])
    assert push(tmp_path).accepted == 0, "the plan shared itself through the token remote"


def _stored() -> dict[str, dict[str, str]]:
    from taskops.usecases import logins

    return logins()
