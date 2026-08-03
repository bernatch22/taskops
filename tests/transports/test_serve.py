"""Many boards on one port: mounting, isolation, and the token that separates them.

Everything here is `Request -> Reply` for the same reason the rest of the HTTP tests are — no
socket, no thread — except the last one, which needs a real feed to prove that two projects on
one process do not see each other's events.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from taskops.transports.cli.commands._serve_init import create
from taskops.transports.http._wire import Request
from taskops.transports.http.projects import mount
from taskops.usecases import init, plan
from taskops.usecases.milestone import open_chapter

TOKENS = {"alpha": "", "beta": ""}


def get(path: str, **headers: str) -> Request:
    return Request(method="GET", path=path, query={}, headers=headers)


def bearer(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}"}


@pytest.fixture
def server(tmp_path: Path) -> Any:
    """A root with two projects, each with its own minted token.

    Every card belongs to a chapter, and these are two SEPARATE boards, so each opens its own —
    a chapter is a fact of one project's log and nothing crosses between them here.
    """
    for name in ("alpha", "beta"):
        TOKENS[name] = _token_of(create(tmp_path / "srv", name))
        open_chapter(tmp_path / "srv" / name, "the chapter these tests plan into",
                     actor="dev:berna")
        plan(tmp_path / "srv" / name, [{"title": f"a task for {name}", "spec": "."}],
             actor="dev:berna")
    return mount(tmp_path / "srv")


def _token_of(printed: str) -> str:
    """`serve init` prints the secret exactly once, and this is the only place it can be read
    from — which is the property being relied on, so reading it here is also the test of it."""
    line = next(part for part in printed.split("\n") if part.strip() and "    " in part)
    return line.strip()


# ---- routing


def test_each_project_answers_under_its_own_prefix(server: Any) -> None:
    for name in ("alpha", "beta"):
        reply = server(get(f"/{name}/api/board", **bearer(TOKENS[name])))
        assert reply.status == 200
        payload = json.loads(reply.body)
        card = next(c for column in payload["columns"] for c in column["cards"])
        assert card["task"]["title"] == f"a task for {name}"


def test_the_ui_is_served_with_the_mount_written_into_its_base_tag(server: Any) -> None:
    """The whole base-path fix in one assertion: the bundle is identical for every project and
    the only thing that differs is this tag, which is what `document.baseURI` then gives the
    frontend so its relative fetches land under the prefix."""
    reply = server(get("/alpha/task/tk-1", **bearer(TOKENS["alpha"])))
    assert reply.status == 200
    if b"ui not built" not in reply.body:
        assert b'<base href="/alpha/"' in reply.body


def test_a_prefix_without_its_slash_redirects_carrying_the_token(server: Any) -> None:
    """`/alpha` and `/alpha/` are different base URLs, and the app mounted at the first one
    would resolve every relative fetch one level too high."""
    request = Request(method="GET", path="/alpha", query={"token": TOKENS["alpha"]}, headers={})
    reply = server(request)
    assert reply.status == 308
    assert reply.headers["Location"] == f"/alpha/?token={TOKENS['alpha']}"


# ---- isolation


def test_one_projects_token_is_refused_by_another(server: Any) -> None:
    """THE reason each project has its own secret. A token is an answer about one board."""
    assert server(get("/beta/api/board", **bearer(TOKENS["alpha"]))).status == 401
    assert server(get("/alpha/api/board", **bearer(TOKENS["beta"]))).status == 401


def test_nothing_at_all_without_a_token(server: Any) -> None:
    """Not even a read. This transport is meant to face the internet, where `taskops ui`'s
    "it is only loopback" is simply untrue."""
    assert server(get("/alpha/api/board")).status == 401
    assert server(get("/alpha/api/config")).status == 401


@pytest.mark.parametrize("path", ["/../etc/passwd", "/..%2F..%2Fetc/api/board",
                                  "/alpha%2F..%2Fbeta/api/board", "/Alpha/api/board",
                                  "/al pha/api/board", "/api/board"])
def test_a_name_that_is_not_a_name_never_reaches_the_filesystem(server: Any, path: str) -> None:
    """The pattern is checked BEFORE a path is built, so traversal is refused as syntax rather
    than caught afterwards by a resolve that somebody could later reorder."""
    assert server(get(path)).status == 404


def test_the_front_page_is_public_and_still_names_no_board(server: Any) -> None:
    """`/` used to be a 404 like any other non-name. It is now the login page — and it is the
    same answer for everyone, so it may not leak the one thing the 404 below protects."""
    reply = server(get("/"))
    assert reply.status == 200
    assert b"alpha" not in reply.body and b"beta" not in reply.body


def test_a_missing_project_is_a_bare_404_that_names_nothing(server: Any) -> None:
    """Listing what does exist would hand an unauthenticated caller every board on the server,
    which is the enumeration the per-project token is there to prevent."""
    reply = server(get("/gamma/api/board"))
    assert reply.status == 404
    assert b"alpha" not in reply.body and b"beta" not in reply.body


def test_a_directory_without_a_project_is_not_served(tmp_path: Path) -> None:
    """`resolve_root` walks UP, so a bare directory under the root would otherwise resolve to
    an ancestor project and serve somebody else's board under its name."""
    # Every card belongs to a chapter: the fixture opens one so the test can be about its own
    # subject rather than about that.
    init(tmp_path, install_git_hooks=False)
    open_chapter(tmp_path, "the chapter these tests plan into",
                 actor="dev:berna")
    (tmp_path / "srv" / "empty").mkdir(parents=True)
    assert mount(tmp_path / "srv")(get("/empty/api/board")).status == 404


def test_a_project_without_a_token_is_not_served_at_all(tmp_path: Path) -> None:
    """Refused rather than served open: the failure mode of the alternative is a public board
    because a file was missing."""
    create(tmp_path / "srv", "alpha")
    (tmp_path / "srv" / "alpha" / "token").unlink()
    assert mount(tmp_path / "srv")(get("/alpha/api/board")).status == 404


# ---- the live feed


@pytest.mark.usefixtures("server")
def test_an_event_in_one_project_never_appears_in_anothers_feed(tmp_path: Path) -> None:
    """The trap this test exists for: the event BUS is process-global, so a write to alpha
    wakes beta's follow. What beta then reads is its OWN sqlite cursor, so the wake-up yields
    nothing — and that is the line that makes one process safe for many projects.
    """
    from taskops.usecases import follow

    feed = follow(tmp_path / "srv" / "beta")
    deadline = time.monotonic() + 5.0
    plan(tmp_path / "srv" / "alpha", [{"title": "written in alpha", "spec": "."}],
         actor="dev:berna")
    seen = []
    while time.monotonic() < deadline and len(seen) < 3:
        event = next(feed)
        if event is not None:
            seen.append(event)
    feed.close()
    assert not seen, f"beta's feed saw alpha's events: {seen}"


# ---- minting


def test_the_token_is_minted_once_and_never_printed_again(tmp_path: Path) -> None:
    first = create(tmp_path / "srv", "alpha")
    token = _token_of(first)
    assert len(token) == 32
    again = create(tmp_path / "srv", "alpha")
    assert token not in again
    assert "already exists" in again


def test_the_token_file_is_not_readable_by_anyone_else(tmp_path: Path) -> None:
    create(tmp_path / "srv", "alpha")
    mode = (tmp_path / "srv" / "alpha" / "token").stat().st_mode & 0o777
    assert mode == 0o600, f"token is {oct(mode)}"


def test_a_project_name_that_is_not_a_url_segment_is_refused(tmp_path: Path) -> None:
    from taskops._errors import TaskopsError

    for bad in ("../escape", "Alpha", "", "a" * 41, "with space"):
        with pytest.raises(TaskopsError):
            create(tmp_path / "srv", bad)


def test_a_served_project_has_no_git_hooks(tmp_path: Path) -> None:
    """A server directory is a store of boards, not a working tree — there is no repository
    here whose commits a hook could bind to."""
    create(tmp_path / "srv", "alpha")
    assert not (tmp_path / "srv" / "alpha" / ".git").exists()
