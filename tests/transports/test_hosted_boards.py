"""Creating a board from a laptop: what GitHub has to say first, and what is left if it says no.

GITHUB IS FAKED, ALWAYS — the same `_fake` the login tests use, for the same reason: a gate
that depended on a network, a rate limit and somebody's real account would fail on a Sunday
for reasons that have nothing to do with this code.

The test that matters most is the last one, and it is a SEAM: `create_hosted` returning a happy
dict proves nothing on its own. What a person checks is that the board they just made ANSWERS —
so the board is created through the use case and then entered through `mount`, with the session
that came back, which is the pair of machines the feature actually spans.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from taskops._errors import BadRequest
from taskops.contracts.hosting import TOKEN_FILE
from taskops.transports.http._wire import Request
from taskops.transports.http.projects import mount
from taskops.usecases._ghlink import read_link
from taskops.usecases.accounts import NoAccess
from taskops.usecases.hosting import create_hosted, create_open
from taskops.usecases.provision import TOKEN_BYTES
from tests.transports.test_accounts import GITHUB_TOKEN, _fake, get, post

SLUG = "bernatch22/tu-repo"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """An EMPTY server root. The whole point is that nobody had to log into it first."""
    home = tmp_path / "srv"
    home.mkdir()
    return home


# ---- the happy path


def test_push_access_to_the_named_repo_creates_and_links_the_board(
        root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The rule, stated once: you may create a board for a repository you can already write to."""
    _fake(monkeypatch, {SLUG: {"push": True}}, login="bernatch22")

    answer = create_hosted(root, GITHUB_TOKEN, "tu-repo", SLUG)

    assert answer["name"] == "tu-repo"
    assert answer["login"] == "bernatch22"
    assert answer["projects"] == ["tu-repo"], "and the session it hands back opens it"
    assert len(answer["session"]) == 32
    assert read_link(root / "tu-repo") == SLUG, "linked at birth, not in a second step"
    assert (root / "tu-repo" / TOKEN_FILE).is_file()


def test_the_board_it_made_actually_answers(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """THE seam. A dict that says "created" is not a board somebody can reach.

    Created through the use case, entered through the mount with the session that came back —
    two machines, which is where every bug of this shape has lived. A board provisioned without
    its store, without its token file or without the link would each pass the test above and
    fail right here.
    """
    _fake(monkeypatch, {SLUG: {"push": True}})
    session = str(create_hosted(root, GITHUB_TOKEN, "tu-repo", SLUG)["session"])

    route = mount(root)
    reply = route(get("/tu-repo/api/board", authorization=f"Bearer {session}"))

    assert reply.status == 200
    assert "columns" in json.loads(reply.body)


def test_the_github_token_is_nowhere_under_the_root(
        root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The claim the login already makes, re-asserted for the door that did not exist then:
    creating a board handles a GitHub credential, and "we don't store it" decays silently."""
    _fake(monkeypatch, {SLUG: {"push": True}})
    create_hosted(root, GITHUB_TOKEN, "tu-repo", SLUG)

    for path in root.rglob("*"):
        if path.is_file():
            assert GITHUB_TOKEN not in path.read_bytes().decode("utf-8", errors="replace"), path


def test_the_list_says_when_each_board_last_moved(
        root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """What makes a list of boards readable rather than an index: which of them is alive.

    The MTIME of the append-only log and not a query — one `stat` per board, so the front page
    costs the same at nine cards as at nine hundred, and it still answers when a board's sqlite
    cache is the broken thing. That last part is why the front page exists at all.
    """
    minted = str(create_open(root, "test")["token"])
    (root / "test" / ".taskops" / "events.jsonl").write_text('{"x":1}\n', encoding="utf-8")

    reply = mount(root)(Request(method="GET", path="/test/api/board",
                                query={"token": minted}, headers={}))
    assert reply.status == 200, "the board is reachable, so the row about it is worth checking"

    # Through the ENDPOINT, with the session resolution stubbed: a session is a GitHub
    # artefact and this board deliberately has none, so there is no other way to reach the row
    # — and reading `_moved` directly would test a `stat` rather than what the page receives.
    monkeypatch.setattr("taskops.transports.http.root.resolve",
                        lambda _home, _bearer: {"login": "nadie", "projects": ["test"]})
    listed = json.loads(mount(root)(get("/api/projects")).body)

    [row] = listed["projects"]
    assert row["updated"] > 0 and row["name"] == "test"


# ---- and the board with no GitHub at all, which is most of them


def test_a_board_can_be_made_with_no_github_anywhere(root: Path) -> None:
    """The three-command start, first command: `remote add`, `board create`, `board invite`.

    No token is passed, no `_fake` is installed, and that is the assertion — this path must not
    reach GitHub even to be refused by it. A checkout with no origin, a repository on a GitLab,
    a directory not in git at all: all of them met "pass --github owner/repo" at the very first
    command, for a server that never needed GitHub to hold a board.
    """
    answer = create_open(root, "test")

    assert answer["name"] == "test" and answer["github"] == ""
    assert len(answer["token"]) == TOKEN_BYTES * 2, "the board's own credential comes back"
    assert (root / "test" / TOKEN_FILE).is_file()


def test_the_creator_can_see_the_board_they_just_made(root: Path) -> None:
    """The session it hands back has to OPEN the board, not merely exist. A session minted over
    the wrong project list is a front page that lists a board you cannot enter."""
    made = create_open(root, "test", "berna")

    listed = json.loads(mount(root)(get("/api/projects",
                                        authorization=f"Bearer {made['session']}")).body)
    entered = mount(root)(get("/test/api/board",
                              authorization=f"Bearer {made['session']}"))

    assert [row["name"] for row in listed["projects"]] == ["test"]
    assert entered.status == 200


def test_the_tokenless_board_answers_with_the_token_it_returned(root: Path) -> None:
    """THE seam, and the bug it was written against: the token has to come back to the CALLER.

    `serve init` prints it on the box; over HTTP there is nobody at the box to read it, so a
    create that provisioned a board and kept its secret would leave the client holding an
    address it cannot write to — a 401 on the very next command, against a board it just made.
    """
    minted = str(create_open(root, "test")["token"])

    # The query form, which is how a browser and `remote.json` both carry it.
    reply = mount(root)(Request(method="GET", path="/test/api/board",
                                query={"token": minted}, headers={}))

    assert reply.status == 200
    assert "columns" in json.loads(reply.body)


def test_the_endpoint_takes_the_tokenless_shape(root: Path) -> None:
    """Branched on the FIELD, not on a mode flag: a client with a repository sends `github`, one
    without cannot, and neither has to be told which door it is standing at."""
    reply = mount(root)(post("/api/boards", {"name": "test", "login": "berna"}))

    assert reply.status == 200
    answer = json.loads(reply.body)
    assert answer["token"] and not answer["github"]
    # A session over THIS board, and it is what makes the board visible at all: sessions are
    # otherwise minted from GitHub, so a board with no repository behind it appeared in nobody's
    # `/api/projects` — you created one and the server's front page did not list it.
    assert answer["session"] and answer["login"] == "berna"


def test_no_create_closes_the_tokenless_door_too(root: Path) -> None:
    """The one that would have been missed. `--no-create` is the WHOLE access control on this
    path — there is no GitHub check behind it — so a flag that shut one door and not the other
    would read as closed and be open."""
    reply = mount(root, create=False)(post("/api/boards", {"name": "test"}))

    assert reply.status == 403
    assert list(root.iterdir()) == []


def test_a_taken_name_is_refused_without_touching_the_board_that_has_it(root: Path) -> None:
    """A second `create test` must not hand the caller a fresh token for somebody else's board
    — that is a board takeover spelled as a convenience."""
    first = str(create_open(root, "test")["token"])

    with pytest.raises(BadRequest) as refused:
        create_open(root, "test")

    assert "already on this server" in str(refused.value)
    assert (root / "test" / TOKEN_FILE).read_text(encoding="utf-8").strip() == first


# ---- the refusals


def test_without_push_access_nothing_is_created(
        root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Order is the invariant: GitHub is asked BEFORE anything is written, so a refused
    request leaves no directory, no store and — the one that would matter — no minted token.

    The disk is asserted FIRST and deliberately. Deleting the push check does not stop this
    raising: `authenticate` refuses at the end too, because an account that cannot push to the
    only linked repository is granted nothing. But by then the board exists. Asserting the
    message first would let that mutation pass as "still refused" while a directory, a store
    and a minted token had already been written for somebody with no access to the repo.
    """
    _fake(monkeypatch, {SLUG: {"push": False, "pull": True}}, login="mirna")

    with pytest.raises(NoAccess) as refused:
        create_hosted(root, GITHUB_TOKEN, "tu-repo", SLUG)

    assert list(root.iterdir()) == [], "a refusal must not leave half a board behind"
    assert SLUG in str(refused.value), "and it must name the repository, not the server"


def test_a_repository_the_account_cannot_see_is_refused_like_any_other(
        root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """GitHub answers 404 for a private repository you are not on, which is the same answer as
    "no access" — treated as one so this is never an existence oracle."""
    _fake(monkeypatch, {})
    with pytest.raises(NoAccess):
        create_hosted(root, GITHUB_TOKEN, "tu-repo", SLUG)


def test_a_name_already_taken_is_refused_rather_than_adopted(
        root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Silently returning the existing board would hand somebody a board that is not theirs,
    with a receipt saying they made it."""
    _fake(monkeypatch, {SLUG: {"push": True}})
    create_hosted(root, GITHUB_TOKEN, "tu-repo", SLUG)

    with pytest.raises(BadRequest) as refused:
        create_hosted(root, GITHUB_TOKEN, "tu-repo", SLUG)
    assert "already on this server" in str(refused.value)


@pytest.mark.parametrize(("name", "slug"), [
    ("Tu-Repo", SLUG),                 # uppercase is not a URL segment
    ("../etc", SLUG),                  # traversal, refused as syntax
    ("", SLUG),
    ("tu-repo", "not-a-slug"),
    ("tu-repo", "../etc/passwd"),
])
def test_a_bad_shape_costs_no_github_call(root: Path, monkeypatch: pytest.MonkeyPatch,
                                          name: str, slug: str) -> None:
    """Both shapes are checked before the network. The slug is pasted into a GitHub URL path,
    so refusing it here is refusing to make the request at all."""
    asked = _fake(monkeypatch, {SLUG: {"push": True}})

    with pytest.raises(BadRequest):
        create_hosted(root, GITHUB_TOKEN, name, slug)
    assert asked == [], "nothing should have been asked of GitHub"


# ---- the endpoint, and the switch that closes it


def test_the_endpoint_creates_and_signs_the_caller_in(
        root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake(monkeypatch, {SLUG: {"push": True}}, login="bernatch22")
    route = mount(root)

    reply = route(post("/api/boards", {"github_token": GITHUB_TOKEN,
                                       "name": "tu-repo", "github": SLUG}))

    assert reply.status == 200
    assert json.loads(reply.body)["name"] == "tu-repo"


def test_no_create_closes_the_door_and_says_who_to_ask(
        root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake(monkeypatch, {SLUG: {"push": True}})
    route = mount(root, create=False)

    reply = route(post("/api/boards", {"github_token": GITHUB_TOKEN,
                                       "name": "tu-repo", "github": SLUG}))

    assert reply.status == 403
    assert "whoever runs it" in json.loads(reply.body)["error"]
    assert list(root.iterdir()) == []


def test_a_readonly_server_refuses_to_mint_a_directory_either(
        root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`--readonly` is "refuse every write". A server that will not accept a comment has no
    business accepting a new board, and leaving that hole open would make the flag a lie."""
    _fake(monkeypatch, {SLUG: {"push": True}})
    route = mount(root, readonly=True)

    reply = route(post("/api/boards", {"github_token": GITHUB_TOKEN,
                                       "name": "tu-repo", "github": SLUG}))

    assert reply.status == 403


def test_the_request_carries_no_username_to_forge(
        root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The security argument, asserted: identity comes back from `/user`, so a body claiming to
    be somebody else changes nothing — there is no field for it to claim in."""
    asked = _fake(monkeypatch, {SLUG: {"push": True}}, login="bernatch22")
    route = mount(root)

    reply = route(post("/api/boards", {"github_token": GITHUB_TOKEN, "name": "tu-repo",
                                       "github": SLUG, "login": "somebody-else"}))

    assert json.loads(reply.body)["login"] == "bernatch22"
    assert "/user" in asked


def test_an_unauthenticated_request_is_refused_by_github_not_by_us(
        root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty token reaches GitHub's own 401, and its sentence is relayed — inventing a
    second one here would hide whether the token was absent, expired or revoked."""
    import urllib.error

    _fake(monkeypatch, {}, boom=urllib.error.HTTPError("/user", 401, "Bad credentials",
                                                       {}, None))  # type: ignore[arg-type]
    route = mount(root)
    reply = route(post("/api/boards", {"github_token": "", "name": "tu-repo", "github": SLUG}))

    assert reply.status == 403
    assert list(root.iterdir()) == []


def test_the_request_shape_is_a_taskops_request() -> None:
    """`post` and `get` come from the login's test module. Named here so the import is not
    mistaken for a leftover: reusing its GitHub fake is what keeps the two doors honest about
    behaving the same way, and a second fake would be a second definition of GitHub."""
    assert isinstance(post("/api/boards", {}), Request)


def test_the_link_rides_on_the_project_list_so_a_client_can_read_it(
        root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A board bound to a repository that is NOT the checkout's origin — the shape a project
    hosted anywhere but GitHub uses to get a real access list.

    `taskops board access` asked the local git remote and answered "not linked to a GitHub
    repository" about a board that was linked. On a question about who can get in, that is the
    worst wrong answer there is, so the link travels with the list the client already fetches.
    """
    _fake(monkeypatch, {SLUG: {"push": True}})
    session = str(create_hosted(root, GITHUB_TOKEN, "codigo-en-gitlab", SLUG)["session"])

    listed = json.loads(mount(root)(get("/api/projects",
                                        authorization=f"Bearer {session}")).body)

    # The link, which is what this test is about — not the row's full shape. See the same
    # relaxation in `test_accounts`: "and no other field" is the one promise this list may
    # never make, because it is the promise that stops it ever gaining one.
    [row] = listed["projects"]
    assert row["name"] == "codigo-en-gitlab" and row["github"] == SLUG


def test_a_server_too_old_to_create_boards_says_so_instead_of_no_such_project(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Hit live against the 0.2.0 box, and the message was about the wrong thing entirely.

    A server with no `/api/boards` falls through to the per-project mount, which reads `api` as
    a board name it does not have and answers `no such project`. True, and a sentence about a
    question nobody asked: the reader's only clue that the SERVER is old is a message that reads
    like a typo in their own command.
    """
    from taskops._errors import TaskopsError
    from taskops.usecases import boards

    def refuse(*_args: object, **_kw: object) -> dict[str, object]:
        raise TaskopsError("no such project")

    monkeypatch.setattr(boards.Wire, "call", refuse)

    with pytest.raises(TaskopsError) as told:
        boards.create_board("https://boards.example.com", GITHUB_TOKEN, "x", SLUG)

    assert "running a taskops older than yours" in str(told.value)
    assert "taskops serve init" in str(told.value), "and it names the way out that does work"


def test_any_other_refusal_is_relayed_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every error string in taskops names what to DO about it, and the server's own sentence
    is the only one that knows why IT said no. Rewriting them all to guess at a version would
    hide a 403 about push access behind advice about upgrading a box."""
    from taskops._errors import TaskopsError
    from taskops.usecases import boards

    def refuse(*_args: object, **_kw: object) -> dict[str, object]:
        raise TaskopsError("the GitHub account mirna cannot push to bernatch22/tu-repo")

    monkeypatch.setattr(boards.Wire, "call", refuse)

    with pytest.raises(TaskopsError) as told:
        boards.create_board("https://boards.example.com", GITHUB_TOKEN, "x", SLUG)
    assert str(told.value) == "the GitHub account mirna cannot push to bernatch22/tu-repo"
