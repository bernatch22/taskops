"""Logging in with GitHub: what grants a board, what does not, and what is never stored.

GITHUB IS FAKED, ALWAYS. `_fake` replaces `urllib.request.urlopen` inside `usecases.accounts`,
so the whole suite stays offline and a test of "the token was rejected" costs microseconds. A
real call here would make the gate depend on a network, a rate limit and somebody's account —
three things that fail on a Sunday for reasons that have nothing to do with the code.
"""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path
from typing import Any

import pytest

from taskops._errors import TaskopsError, Unreachable
from taskops.transports.cli.commands._serve_init import create
from taskops.transports.cli.commands._serve_link import link
from taskops.transports.http._wire import Request
from taskops.transports.http.projects import mount
from taskops.usecases import _sessions, accounts
from taskops.usecases.accounts import NoAccess

GITHUB_TOKEN = "gho_a_token_that_must_never_be_written_down"


def get(path: str, **headers: str) -> Request:
    return Request(method="GET", path=path, query={}, headers=headers)


def post(path: str, payload: dict[str, Any]) -> Request:
    return Request(method="POST", path=path, query={}, headers={},
                   body=json.dumps(payload).encode("utf-8"))


class _Answer(io.BytesIO):
    def __enter__(self) -> "_Answer":
        return self

    def __exit__(self, *_: object) -> None:
        return None


def _fake(monkeypatch: pytest.MonkeyPatch, repos: dict[str, Any], *, login: str = "jp",
          boom: Exception | None = None) -> list[str]:
    """Stand in for GitHub. `repos` maps `owner/repo` to the `permissions` dict it answers
    with; anything absent is a 404, exactly as a repository you cannot see. Returns the list
    of paths asked for, so a test can assert the token never went anywhere else."""
    asked: list[str] = []

    def urlopen(request: Any, timeout: float = 0) -> _Answer:  # noqa: ARG001
        path = str(request.full_url).removeprefix(accounts.API)
        asked.append(path)
        assert request.get_header("User-agent"), "github refuses a request with no User-Agent"
        if boom is not None:
            raise boom
        if path == "/user":
            return _Answer(json.dumps({"login": login}).encode())
        slug = path.removeprefix("/repos/")
        if slug not in repos:
            raise urllib.error.HTTPError(path, 404, "Not Found", {}, None)  # type: ignore[arg-type]
        return _Answer(json.dumps({"permissions": repos[slug]}).encode())

    monkeypatch.setattr(accounts.urllib.request, "urlopen", urlopen)
    return asked


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """Two projects: `axion` linked to a repository, `beta` not linked at all."""
    home = tmp_path / "srv"
    for name in ("axion", "beta"):
        create(home, name)
    link(home, "axion", slug="cloudacio/Axion")
    return home


# ---- the login


def test_push_access_to_the_linked_repo_mints_a_session_for_that_project(
        root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """THE acceptance case: an account with push on cloudacio/Axion ends up inside /axion/."""
    _fake(monkeypatch, {"cloudacio/Axion": {"push": True}}, login="jpolivera")
    answer = accounts.authenticate(root, GITHUB_TOKEN)
    assert answer["login"] == "jpolivera"
    assert answer["projects"] == ["axion"]
    assert len(answer["session"]) == 32


def test_read_access_is_not_enough(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`push` and not `pull`: reading a repository is not being on the team that runs it."""
    _fake(monkeypatch, {"cloudacio/Axion": {"push": False, "pull": True}})
    with pytest.raises(NoAccess):
        accounts.authenticate(root, GITHUB_TOKEN)


def test_a_repo_the_account_cannot_see_is_not_a_grant(
        root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A private repository answers 404 rather than 403, which is GitHub declining to confirm
    it exists. Treated as "not yours" so the board never becomes an existence oracle."""
    with pytest.raises(NoAccess):
        _fake(monkeypatch, {})
        accounts.authenticate(root, GITHUB_TOKEN)


def test_an_unlinked_project_is_never_granted(
        root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`beta` has no link, so no GitHub answer can open it — it stays token-only."""
    _fake(monkeypatch, {"cloudacio/Axion": {"push": True}})
    assert accounts.authenticate(root, GITHUB_TOKEN)["projects"] == ["axion"]


def test_github_not_answering_is_a_502_and_not_a_refusal(
        root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake(monkeypatch, {}, boom=urllib.error.URLError("name resolution failed"))
    with pytest.raises(Unreachable) as raised:
        accounts.authenticate(root, GITHUB_TOKEN)
    assert raised.value.http_status == 502


def test_a_rate_limit_comes_back_in_githubs_own_words(
        root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The one sentence that says what happened is GitHub's, so it is relayed verbatim."""
    body = io.BytesIO(json.dumps({"message": "API rate limit exceeded"}).encode())
    _fake(monkeypatch, {}, boom=urllib.error.HTTPError(
        "/user", 403, "Forbidden", {}, body))  # type: ignore[arg-type]
    with pytest.raises(TaskopsError) as raised:
        accounts.authenticate(root, GITHUB_TOKEN)
    assert "API rate limit exceeded" in str(raised.value)


def test_an_empty_token_never_reaches_github(
        root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asked = _fake(monkeypatch, {"cloudacio/Axion": {"push": True}})
    with pytest.raises(TaskopsError):
        accounts.authenticate(root, "   ")
    assert not asked


# ---- what the login leaves behind


def test_the_github_token_is_never_written_down(
        root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The claim in `accounts`'s docstring, as an assertion — over EVERY file the server root
    holds, because "we only write it to sessions.json" is a thing that stops being true."""
    _fake(monkeypatch, {"cloudacio/Axion": {"push": True}})
    accounts.authenticate(root, GITHUB_TOKEN)
    for path in root.rglob("*"):
        if path.is_file():
            assert GITHUB_TOKEN not in path.read_bytes().decode("utf-8", "replace"), path


def test_the_sessions_file_is_not_readable_by_anyone_else(
        root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake(monkeypatch, {"cloudacio/Axion": {"push": True}})
    accounts.authenticate(root, GITHUB_TOKEN)
    mode = (root / _sessions.SESSIONS_FILE).stat().st_mode & 0o777
    assert mode == 0o600, oct(mode)


def test_a_session_expires_and_an_expired_one_is_pruned_when_the_next_is_written(
        root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Checked on read, applied on write — so expiry is true on a server nobody has touched."""
    at = [1_000_000.0]
    monkeypatch.setattr(_sessions, "now", lambda: at[0])
    old = _sessions.mint(root, "jp", ["axion"])
    at[0] += _sessions.TTL + 1
    assert _sessions.resolve(root, old) is None
    fresh = _sessions.mint(root, "jp", ["axion"])
    stored = json.loads((root / _sessions.SESSIONS_FILE).read_text(encoding="utf-8"))
    assert list(stored) == [fresh]


# ---- the session on the wire


@pytest.fixture
def server(root: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    _fake(monkeypatch, {"cloudacio/Axion": {"push": True}}, login="jpolivera")
    return mount(root)


def test_the_root_endpoints_mint_a_session_and_then_list_what_it_opens(server: Any) -> None:
    reply = server(post("/api/auth/github", {"github_token": GITHUB_TOKEN}))
    assert reply.status == 200
    minted = json.loads(reply.body)
    assert minted["projects"] == ["axion"]
    listed = server(get("/api/projects", authorization=f"Bearer {minted['session']}"))
    assert listed.status == 200
    assert json.loads(listed.body) == {"login": "jpolivera",
                                       "projects": [{"name": "axion", "path": "/axion/"}]}


def test_a_session_opens_the_board_of_the_project_it_lists(server: Any) -> None:
    """The point of all of it: no project token anywhere, and the board answers."""
    minted = json.loads(server(post("/api/auth/github",
                                    {"github_token": GITHUB_TOKEN})).body)["session"]
    assert server(get("/axion/api/board", authorization=f"Bearer {minted}")).status == 200


def test_a_session_does_not_open_a_project_it_does_not_list(server: Any) -> None:
    minted = json.loads(server(post("/api/auth/github",
                                    {"github_token": GITHUB_TOKEN})).body)["session"]
    assert server(get("/beta/api/board", authorization=f"Bearer {minted}")).status == 401


def test_an_expired_session_is_refused_by_the_board_and_by_the_listing(
        server: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    minted = json.loads(server(post("/api/auth/github",
                                    {"github_token": GITHUB_TOKEN})).body)["session"]
    monkeypatch.setattr(_sessions, "now", lambda: 10 ** 12)
    assert server(get("/axion/api/board", authorization=f"Bearer {minted}")).status == 401
    assert server(get("/api/projects", authorization=f"Bearer {minted}")).status == 401


def test_a_login_that_grants_nothing_is_a_403_that_says_what_to_do(
        root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake(monkeypatch, {"cloudacio/Axion": {"push": False}})
    reply = mount(root)(post("/api/auth/github", {"github_token": GITHUB_TOKEN}))
    assert reply.status == 403
    assert b"push access" in reply.body


# ---- the front page


def test_the_root_page_lists_nothing_without_a_session(server: Any) -> None:
    """Served to anyone, it is an instruction and not an index — naming the boards would hand
    every visitor the enumeration the per-project 404 exists to deny."""
    reply = server(get("/"))
    assert reply.status == 200
    assert b"taskops login" in reply.body
    assert b"axion" not in reply.body and b"beta" not in reply.body


def test_the_page_carries_no_credential_at_all(server: Any, root: Path) -> None:
    """No project token baked into the HTML — the page is public by construction."""
    page = server(get("/")).body
    assert _token_of(root / "axion").encode() not in page
    assert GITHUB_TOKEN.encode() not in page


# ---- the machine credential is untouched


def test_the_project_token_still_opens_the_board_on_its_own(root: Path) -> None:
    """Push, pull and every agent authenticate with this — a login is an ADDITION, and a
    change that broke this would break replication on a server nobody logged into."""
    token = _token_of(root / "axion")
    assert mount(root)(get("/axion/api/board", authorization=f"Bearer {token}")).status == 200


def test_a_project_token_is_not_a_session(root: Path) -> None:
    token = _token_of(root / "axion")
    assert mount(root)(get("/api/projects", authorization=f"Bearer {token}")).status == 401


def _token_of(project: Path) -> str:
    return (project / "token").read_text(encoding="utf-8").strip()


# ---- the link


def test_link_shows_sets_and_removes(root: Path) -> None:
    assert "cloudacio/Axion" in link(root, "axion")
    assert "not linked" in link(root, "beta")
    link(root, "beta", slug="cloudacio/other")
    assert "cloudacio/other" in link(root, "beta")
    assert "no longer linked" in link(root, "beta", remove=True)
    assert "not linked" in link(root, "beta")


@pytest.mark.parametrize("bad", ["Axion", "owner/repo/extra", "../etc", "owner repo", "/"])
def test_a_slug_that_is_not_owner_slash_repo_is_refused(root: Path, bad: str) -> None:
    """Checked where a person can see the typo, and before it is ever pasted into a URL."""
    with pytest.raises(TaskopsError):
        link(root, "axion", slug=bad)


def test_linking_something_that_is_not_a_project_here_is_refused(root: Path) -> None:
    """`locate` walks UP, so a bare directory would resolve to an ancestor project and the
    link would grant a board nobody named."""
    (root / "loose").mkdir()
    with pytest.raises(TaskopsError):
        link(root, "loose", slug="cloudacio/Axion")
