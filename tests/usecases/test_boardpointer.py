"""`.taskops/board.json` — the address a clone carries, and `taskops join` with no arguments.

The step this deletes is the one `git clone` famously does not have: a teammate should not need
a URL pasted from a chat to reach the board of the repository they already have. So the address
travels WITH the repository, committed, holding no secret — and the ignore block has to keep
letting it, which is what the last test here is about.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskops._errors import BadRequest
from taskops.usecases import init
from taskops.usecases._boardfile import pointer_path, read_pointer, write_pointer
from taskops.usecases.boards import name_from, origin_slug
from taskops.usecases.join import join

URL = "https://taskops.example.com/tu-repo"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    init(tmp_path, install_git_hooks=False)
    return tmp_path


# ---- the file


def test_the_pointer_round_trips(repo: Path) -> None:
    write_pointer(repo, URL + "/")
    assert read_pointer(repo) == URL, "a trailing slash is not part of an address"


def test_a_repository_with_no_pointer_answers_empty(repo: Path) -> None:
    assert read_pointer(repo) == ""


def test_a_malformed_pointer_is_not_fatal(repo: Path) -> None:
    """It arrives through `git pull` from however many taskops versions a team runs. A board
    nobody can join is a better failure than a command that cannot start."""
    pointer_path(repo).write_text("{not json", encoding="utf-8")
    assert read_pointer(repo) == ""


def test_it_holds_no_credential(repo: Path) -> None:
    """The entire reason it may be committed. `remote.json` is the file with the secret, and
    the two live one line apart in the ignore block — see `_gitignore.BOARD_NOTE`."""
    write_pointer(repo, URL)
    assert pointer_path(repo).read_text(encoding="utf-8").strip() == (
        '{\n  "url": "https://taskops.example.com/tu-repo"\n}')


# ---- join


def _offline_join(repo: Path, url: str = "") -> None:
    """Join, tolerating the first pull failing because there is no server in a unit test.

    The pull is attempted whenever a credential exists — a token on the URL or a session for
    the server — and the address is recorded BEFORE it, on purpose: a join interrupted by a
    network is a repository that still knows where its board is, and re-running finishes it.
    That a join with a session ends on a filled board is asserted where a real server exists,
    in `tests/e2e/test_the_real_topology.py`.
    """
    from taskops._errors import Unreachable

    with pytest.raises(Unreachable):
        join(repo, url)


@pytest.fixture
def signed_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A session for that server, in a scratch home so no test writes the developer's own."""
    from taskops.usecases._sessionfile import save_session

    monkeypatch.setenv("TASKOPS_HOME", str(tmp_path / "home"))
    save_session("https://taskops.example.com/tu-repo", "a" * 32, "ana")


@pytest.mark.usefixtures("signed_in")
def test_joining_by_url_writes_the_pointer_for_everybody_after(repo: Path) -> None:
    """The first person to join still pastes a link. Nobody else has to."""
    _offline_join(repo, URL)
    assert read_pointer(repo) == URL


def test_the_token_on_the_url_is_dropped_from_the_pointer(repo: Path) -> None:
    """A board URL is shared with `?token=` on it. Committing that would put a bearer in git,
    which is the one thing this file may never hold.

    The first pull cannot reach a server that does not exist, and that is incidental — the
    address is recorded before it is attempted, on purpose: a join interrupted by a network is
    a repository that still knows where its board is, and re-running finishes the job.
    """
    _offline_join(repo, URL + "?token=abc123")
    assert read_pointer(repo) == URL
    assert "abc123" not in pointer_path(repo).read_text(encoding="utf-8")


@pytest.mark.usefixtures("signed_in")
def test_joining_with_no_url_reads_what_the_clone_carries(repo: Path) -> None:
    write_pointer(repo, URL)
    _offline_join(repo)
    assert read_pointer(repo) == URL, "it used the address it carried, and kept it"


def test_joining_without_a_session_names_the_server_to_log_into(repo: Path) -> None:
    """Found by this test and fixed because of it: the refusal came from `add_remote`, whose
    sentence is written for somebody configuring a remote by hand — it said "run `taskops login
    <server-url>`" without naming one, and the obvious guess is the BOARD url, which is exactly
    the address login rejects. The server is the board URL minus its last segment."""
    write_pointer(repo, URL)
    with pytest.raises(BadRequest) as refused:
        join(repo)
    assert "taskops login https://taskops.example.com\n" in str(refused.value)


def test_joining_with_nothing_to_go_on_says_how_to_get_one(repo: Path) -> None:
    """The refusal a person hits after cloning a repository whose board was never committed.
    It names both ways out, because they are different situations: somebody has the URL, or
    nobody has made the board yet."""
    with pytest.raises(BadRequest) as refused:
        join(repo)
    assert "taskops join <url>" in str(refused.value)
    assert "taskops board create" in str(refused.value)


def test_the_pointer_is_not_gitignored(tmp_path: Path) -> None:
    """The mechanism the whole feature rests on: the block lists paths rather than ignoring
    `.taskops/` wholesale, so this file is tracked by default. A tidy-up that replaced those
    lines with a wildcard would silently take argument-less `join` away from every clone."""
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True)
    init(tmp_path, install_git_hooks=False)
    write_pointer(tmp_path, URL)

    done = subprocess.run(["git", "check-ignore", ".taskops/board.json"],
                          cwd=tmp_path, capture_output=True, text=True, check=False)
    assert done.returncode != 0, "board.json must be committable — it is the address, not a key"


# ---- reading the checkout, which is what makes `board create` argument-less


@pytest.mark.parametrize(("origin", "slug"), [
    ("git@github.com:bernatch22/tu-repo.git", "bernatch22/tu-repo"),
    ("https://github.com/bernatch22/tu-repo.git", "bernatch22/tu-repo"),
    ("https://github.com/bernatch22/tu-repo", "bernatch22/tu-repo"),
    ("ssh://git@github.com/bernatch22/tu-repo.git", "bernatch22/tu-repo"),
    ("git@gitlab.com:bernatch22/tu-repo.git", ""),
    ("https://github.com/bernatch22", ""),
    ("", ""),
])
def test_the_origin_is_read_in_both_shapes_github_hands_out(
        tmp_path: Path, origin: str, slug: str) -> None:
    """A team uses both `git@` and `https://` and neither is the wrong one. Anything that is
    not GitHub answers "" so the caller can ask for `--github` — a better sentence than a slug
    guessed out of a GitLab URL."""
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True)
    if origin:
        subprocess.run(["git", "remote", "add", "origin", origin],
                       cwd=tmp_path, check=True, capture_output=True)
    assert origin_slug(tmp_path) == slug


@pytest.mark.parametrize(("slug", "name"), [
    ("bernatch22/tu-repo", "tu-repo"),
    ("bernatch22/My-Repo", "my-repo"),
    ("bernatch22/some_thing.v2", "some-thing-v2"),
    ("bernatch22/---", ""),
])
def test_the_board_name_defaults_to_the_repositorys(slug: str, name: str) -> None:
    """`NAME` refuses uppercase, dots and underscores, and a person who has to be told twice
    which characters are legal is a person the tool failed."""
    if not name:
        with pytest.raises(BadRequest):
            name_from(slug)
        return
    assert name_from(slug) == name
