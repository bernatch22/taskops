"""THE seam test: a real HTTP server on a real port, two real clients.

Every bug worth its own test in v1 lived between two machines — twelve in three
days, all invisible to tests that used a single store. So this file never uses
`Stores` directly: it talks to `RemoteBoard`, over a socket, like an agent does.
"""

from __future__ import annotations

import json
import socket
import threading
from base64 import b64encode
from typing import Any, BinaryIO, Iterator
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

import taskops
from taskops import _clock
from taskops.http import feed
from taskops.board import RemoteBoard
from tests.conftest import T0
from taskops._errors import Refused, BadRequest, Unreachable, TaskopsError
from taskops.http.server import BoardServer, serve

BOARD = "facturador"
BERNA = "dev:berna"
ANA = "dev:ana"
W1 = "agent:berna/w1"
W2 = "agent:berna/w2"

pytestmark = pytest.mark.usefixtures("clock")


@pytest.fixture()
def server(tmp_path: Path) -> Iterator[BoardServer]:
    httpd = serve(tmp_path / "boards", "127.0.0.1", 0)
    httpd.mounts.create(BOARD)  # a board exists because somebody made it, never by asking
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def url_of(httpd: BoardServer, board: str = BOARD) -> str:
    return f"http://127.0.0.1:{httpd.server_address[1]}/{board}"


def client(httpd: BoardServer, actor: str, subject: str | None = None) -> RemoteBoard:
    token, _ = httpd.mounts.credentials.mint(subject or actor, BOARD, _clock.now())
    return RemoteBoard(url_of(httpd), token, actor)


def plan(board: RemoteBoard) -> list[dict[str, Any]]:
    out = board.call(
        "plan",
        {
            "milestone": "MVP facturador",
            "goal": "read a bank CSV and issue invoices with VAT",
            "tasks": [
                {"title": "invoice model", "spec": "the Invoice dataclass", "files": ["m.py"]},
                {"title": "CSV parser", "spec": "read the export", "files": ["p.py"]},
                {"title": "VAT", "spec": "compute it", "files": ["t.py"], "after": 0},
            ],
        },
    )
    return out["cards"]


# ── the whole cycle, over the wire ──────────────────────────────────────────


def test_plan_dispatch_take_commit_done_merge(server: BoardServer) -> None:
    dev = client(server, BERNA)
    worker = client(server, W1, subject=BERNA)  # a dev credential may act as its own agent

    cards = plan(dev)
    briefs = dev.call("assign", {"tasks": [cards[0]["id"]]})["briefs"]
    assert briefs[0]["actor"] == W1 and briefs[0]["base"] == "ms/mvp-facturador"

    taken = worker.call("take", {"task": cards[0]["id"]})
    assert taken["milestone"]["goal"].startswith("read a bank CSV")
    assert taken["worktree"] == f".taskops/trees/{cards[0]['id']}"

    worker.call("bind", {"task": cards[0]["id"], "sha": "a1b2", "subject": "feat: model"})
    worker.call("update", {"task": cards[0]["id"], "status": "done", "comment": "model + tests"})
    merged = dev.call("merged", {"task": cards[0]["id"], "sha": "9c2f"})
    assert merged["into"] == "ms/mvp-facturador"

    board = dev.call("board", {})
    assert board["groups"]["merge"] == []
    assert [c["title"] for c in board["groups"]["take"]] == ["CSV parser", "VAT"]


def test_two_clients_race_for_one_card_and_only_one_wins(server: BoardServer) -> None:
    dev = client(server, BERNA)
    first = client(server, W1, subject=BERNA)
    second = client(server, W2, subject=BERNA)
    cards = plan(dev)

    first.call("take", {"task": cards[0]["id"]})
    with pytest.raises(Refused, match="held by agent:berna/w1"):
        second.call("take", {"task": cards[0]["id"]})


def test_a_write_that_cannot_reach_the_server_never_degrades(server: BoardServer) -> None:
    """v1 fell back to a local store and two machines each owned the same card."""
    dev = client(server, BERNA)
    plan(dev)
    server.shutdown()
    server.server_close()
    with pytest.raises(Unreachable, match="did not answer"):
        dev.call("update", {"task": "tk-000000", "comment": "hello?"})


# ── the envelope and the wall ───────────────────────────────────────────────


def test_every_answer_is_an_object_with_ok_and_seq(server: BoardServer) -> None:
    dev = client(server, BERNA)
    plan(dev)
    raw = _post(url_of(server), _token(server, BERNA), {"verb": "board", "actor": BERNA})
    assert raw["ok"] is True and isinstance(raw["data"], dict) and raw["seq"] > 0


def test_the_role_wall_holds_across_the_wire(server: BoardServer) -> None:
    dev = client(server, BERNA)
    worker = client(server, W1, subject=BERNA)
    cards = plan(dev)
    with pytest.raises(Refused, match="taskops_assign"):
        dev.call("take", {"task": cards[0]["id"]})
    with pytest.raises(Refused, match="do not plan"):
        worker.call("plan", {"tasks": []})


def test_actor_on_the_call_crosses_the_wire_and_the_credential_rules_it(
    server: BoardServer,
) -> None:
    """One RemoteBoard (the session's), two identities: the orchestrator's own,
    and actor= per call for the workers it spawned. The credential is the judge:
    a dev may act as its own agents and as nobody else's."""
    dev = client(server, BERNA)
    cards = plan(dev)
    dev.call("assign", {"tasks": [cards[0]["id"]], "workers": ["w1"]})

    taken = dev.call("take", {"task": cards[0]["id"], "actor": W1})
    assert taken["state"] == "doing"
    assert taken["lease"]["actor"] == W1  # the claim is the worker's, not the session's

    with pytest.raises(Refused, match="may not act as"):
        dev.call("board", {"actor": "agent:ana/w9"})  # somebody else's worker


def test_a_credential_may_not_impersonate_another_person(server: BoardServer) -> None:
    ana = client(server, ANA)
    ana.actor = BERNA  # a client can claim anything; the server is what decides
    with pytest.raises(Refused, match="may not act as"):
        ana.call("board", {})


def test_an_unknown_or_revoked_credential_says_how_to_join(server: BoardServer) -> None:
    stranger = RemoteBoard(url_of(server), "not-a-token", BERNA)
    with pytest.raises(Refused, match="taskops join"):
        stranger.call("board", {})

    token, credential = server.mounts.credentials.mint(BERNA, BOARD, _clock.now())
    server.mounts.credentials.revoke(credential.id)
    with pytest.raises(Refused, match="revoked"):
        RemoteBoard(url_of(server), token, BERNA).call("board", {})


def test_an_invite_is_single_use_and_mints_a_personal_credential(server: BoardServer) -> None:
    invite, _ = server.mounts.credentials.mint(
        "invite:ana", BOARD, _clock.now(), caps="read,write", once=True
    )
    got = _redeem(url_of(server), invite, "ana")
    assert got["actor"] == "dev:ana"
    RemoteBoard(url_of(server), got["token"], ANA).call("board", {})  # the new one works
    with pytest.raises(Refused, match="revoked"):
        _redeem(url_of(server), invite, "ana")  # the invite is burned


def test_a_board_name_outside_the_pattern_never_touches_disk(server: BoardServer) -> None:
    token = _token(server, BERNA)
    base = f"http://127.0.0.1:{server.server_address[1]}/.."
    with pytest.raises(BadRequest, match="names are"):
        RemoteBoard(base, token, BERNA).call("board", {})
    # And it was refused BEFORE any path was joined: the root holds the server's
    # own credential store and the ONE board the fixture created, nothing else.
    assert sorted(p.name for p in server.mounts.root.iterdir()) == [BOARD, "live.sqlite"]


# ── no board comes into existence by accident ───────────────────────────────


def test_an_unknown_board_is_404_and_leaves_nothing_on_disk(server: BoardServer) -> None:
    """The hole this card closed, found 2026-08-08 and left unprobed because
    probing it meant writing to production.

    `mounts.stores()` did `Stores(self.root / name)` for ANY name matching the
    pattern, and `Stores` makes its own directory. The router calls
    `mounts.check(board)` BEFORE `self._credential(...)`, so the request below —
    no token at all, a name nobody has ever used — used to leave
    `<root>/ghostboard/` with a cache and a lease file in it. A stranger's
    question caused a write, which is precisely what this chapter's rules forbid.
    """
    before = sorted(p.name for p in server.mounts.root.iterdir())
    ghost = "ghostboard"
    status, body = _get_post(
        f"http://127.0.0.1:{server.server_address[1]}/{ghost}",
        "",  # anonymous ON PURPOSE: the mount used to happen before auth
        {"verb": "board", "actor": BERNA},
    )

    assert status == 404 and body["error"]["code"] == "not_found"
    assert "never by a request for one" in body["error"]["message"]
    # THE assertion of this test: no side effect, at all.
    assert not (server.mounts.root / ghost).exists()
    assert sorted(p.name for p in server.mounts.root.iterdir()) == before


def test_a_board_only_exists_because_somebody_created_it(server: BoardServer) -> None:
    """The other half: creation is a door, and it is not the reading path.

    `create()` is what a server-scope `board.create` (owner only) will call; a
    board it made is then readable through the ordinary mount, exactly as the
    fixture's own board is."""
    fresh = "segundo"
    assert not (server.mounts.root / fresh).exists()
    server.mounts.create(fresh)
    assert (server.mounts.root / fresh).is_dir()
    token, _ = server.mounts.credentials.mint(BERNA, "*", _clock.now())
    base = f"http://127.0.0.1:{server.server_address[1]}/{fresh}"
    status, body = _get_post(base, token, {"verb": "board", "actor": BERNA})
    assert status == 200 and body["data"]["groups"]["take"] == []


def test_a_feed_for_an_unknown_board_creates_nothing_either(server: BoardServer) -> None:
    """/feed and /git take the same `check` door as /rpc. One wall, not three —
    a second copy of the existence test is how one of them would drift open."""
    for tail in ("feed", "git/commit/HEAD"):
        status, body = _get(
            f"http://127.0.0.1:{server.server_address[1]}/nadie/{tail}", _token(server, BERNA)
        )
        assert status == 404, tail
        assert "no board named" in body["error"]["message"], tail
    assert not (server.mounts.root / "nadie").exists()


# ── the server knows who owns it ────────────────────────────────────────────


PUBKEY = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJ3Fm5NcJ5PRD2G0oO7CjGPXk1kYaU2SQlHkzZ9pQ1aB berna@air"
)
PUBKEY2 = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIB8sQ0mgLZ3nS4z0nCq0oV5tXHhYw2mBQ9nTgqJ7cKdE laptop"
)


def test_server_init_records_the_owner_and_writes_allowed_signers(tmp_path: Path) -> None:
    """Criterion 2. The bootstrap, run as the CLI runs it — the one act over ssh."""
    from taskops.cli import admin
    from taskops.store.server import SIGNERS, ServerStore

    root = tmp_path / "boards"
    (tmp_path / "id.pub").write_text(PUBKEY, encoding="utf-8")
    assert admin.init(root, str(tmp_path / "id.pub"), "berna") == 0

    store = ServerStore(root)
    try:
        owner = store.owner()
        assert owner is not None and owner == ("berna", "owner")
        assert store.role_of("berna") == "owner"
        assert store.role_of("nobody") == "anon"  # unregistered is an ANSWER, not an error
        signers = (root / SIGNERS).read_text(encoding="utf-8")
        # The exact format `ssh-keygen -Y verify` consumes: principal, type, key.
        assert signers == "berna ssh-ed25519 " + PUBKEY.split()[1] + "\n"
        assert "berna@air" not in signers  # the comment is a label, not identity
        assert store.keys()[0].fingerprint.startswith("SHA256:")
    finally:
        store.close()


def test_allowed_signers_is_regenerated_from_the_store_on_every_change(tmp_path: Path) -> None:
    """Criterion 3. The file is `cache.sqlite` to the store's `events.jsonl`:
    derived, never appended to, and a hand edit does not survive the next write."""
    from taskops.store.server import SIGNERS, ServerStore

    root = tmp_path / "boards"
    store = ServerStore(root)
    try:
        first = store.enroll("berna", "owner", PUBKEY, _clock.now())
        store.enroll("ana", "member", PUBKEY2, _clock.now())
        assert (root / SIGNERS).read_text().splitlines() == [
            "ana ssh-ed25519 " + PUBKEY2.split()[1],
            "berna ssh-ed25519 " + PUBKEY.split()[1],
        ]

        (root / SIGNERS).write_text("mallory ssh-ed25519 AAAA\n", encoding="utf-8")
        store.revoke_key(first.fingerprint)
        # Regenerated WHOLE: the revoked key is gone AND so is the hand edit.
        assert (root / SIGNERS).read_text().splitlines() == [
            "ana ssh-ed25519 " + PUBKEY2.split()[1]
        ]
        assert [k.principal for k in store.keys()] == ["ana"]
        # ...and re-opening the store rebuilds the file from the same truth.
        (root / SIGNERS).unlink()
    finally:
        store.close()
    again = ServerStore(root)
    try:
        assert (root / SIGNERS).read_text().splitlines() == [
            "ana ssh-ed25519 " + PUBKEY2.split()[1]
        ]
    finally:
        again.close()


def test_the_store_refuses_a_second_owner_and_a_key_with_no_principal(tmp_path: Path) -> None:
    from taskops.store.server import ServerStore

    store = ServerStore(tmp_path / "boards")
    try:
        store.enroll("berna", "owner", PUBKEY, _clock.now())
        with pytest.raises(Refused, match="already owned by 'berna'"):
            store.enroll("mallory", "owner", PUBKEY2, _clock.now())
        with pytest.raises(Refused, match="the owner registers one"):
            store.add_key("ghost", PUBKEY2, _clock.now())
        with pytest.raises(BadRequest, match="not an ssh public key"):
            store.add_key("berna", "-----BEGIN OPENSSH PRIVATE KEY-----", _clock.now())
    finally:
        store.close()


def test_a_server_scope_refusal_names_the_role_that_may(tmp_path: Path) -> None:
    """Criterion 4, and the milestone's house rule: the refusal to an unkeyed
    writer says how a key gets registered."""
    from taskops.core import scope

    scope.permit("board.read", scope.ROLE_ANON)  # anonymous read is a read
    scope.permit("board.create", scope.ROLE_OWNER)
    with pytest.raises(Refused, match="owner may"):
        scope.permit("board.create", scope.ROLE_MEMBER)
    with pytest.raises(Refused) as caught:
        scope.permit("board.write", scope.ROLE_ANON)
    assert "member or owner may" in str(caught.value)
    assert "taskops server key add" in str(caught.value)  # the way IN, not just the no
    with pytest.raises(Refused, match="unknown server operation"):
        scope.permit("board.destroy", scope.ROLE_OWNER)


# ── the live feed ───────────────────────────────────────────────────────────


def test_the_feed_pokes_the_ui_after_the_write_is_durable(server: BoardServer) -> None:
    """A signal, not a payload: the UI refetches, so it cannot show a stale row."""
    dev = client(server, BERNA)
    stream = urlopen(f"{url_of(server)}/feed?token={_token(server, BERNA)}", timeout=5)
    assert b"hello" in stream.readline() + stream.readline()

    plan(dev)
    seen: list[dict[str, Any]] = []
    while len(seen) < 1:
        line = stream.readline().decode().strip()
        if line.startswith("data:"):
            payload: Any = json.loads(line[5:])
            if payload.get("type") == "change":
                seen.append(payload)
    assert seen[0]["verb"] == "plan" and seen[0]["seq"] > 0
    stream.close()


def test_the_feed_also_pokes_for_a_write_this_process_never_saw(
    server: BoardServer, tmp_path: Path
) -> None:
    """The LOCAL setup, which is the common one: every agent's MCP server writes
    through its own `LocalBoard`, straight to the same files, in its own
    process. Publishing only from the RPC handler meant the socket connected,
    reported "live", and stayed mute for the whole session — a live board that
    needed a manual reload. The board's own sequence is the signal.
    """
    from taskops.board import LocalBoard

    stream = urlopen(f"{url_of(server)}/feed?token={_token(server, BERNA)}", timeout=5)
    assert b"hello" in stream.readline() + stream.readline()

    dev = LocalBoard(server.mounts.root / BOARD, BERNA)  # NOT over HTTP
    try:
        dev.call("plan", {"milestone": "M", "goal": "g", "tasks": [{"title": "found it"}]})
    finally:
        dev.close()

    # Bounded by LINES, not by the clock: this suite freezes time, and the
    # stream keeps emitting `: ping` forever, so a deadline made of `now()`
    # would hang the run rather than fail it. The watcher polls once a second
    # and the server pings every two, so a handful of lines is generous.
    seen: dict[str, Any] = {}
    for _ in range(12):
        line = stream.readline().decode().strip()
        if line.startswith("data:"):
            payload: Any = json.loads(line[5:])
            if payload.get("type") == "change":
                seen = payload
                break
    assert seen.get("seq", 0) > 0, "the board moved and the page was never told"
    stream.close()


def test_the_websocket_upgrade_is_a_real_handshake(server: BoardServer) -> None:
    """A browser only accepts a 101 over HTTP/1.1 with the right accept key.

    This is tested at the socket, not through a library, because the failure it
    guards against is invisible from Python: the UI connects, gets a 1.0 status
    line, and quietly never goes live.
    """
    dev = client(server, BERNA)
    key = b64encode(b"0123456789abcdef").decode()
    sock = socket.create_connection(("127.0.0.1", server.server_address[1]), timeout=5)
    sock.sendall(
        f"GET /{BOARD}/feed?token={_token(server, BERNA)} HTTP/1.1\r\n"
        f"Host: 127.0.0.1\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n".encode()
    )
    stream = sock.makefile("rb")
    status = stream.readline().decode().strip()
    headers: dict[str, str] = {}
    while True:
        line = stream.readline().decode().strip()
        if not line:
            break
        name, _, value = line.partition(":")
        headers[name.lower()] = value.strip()

    assert status == "HTTP/1.1 101 Switching Protocols"
    assert headers["upgrade"].lower() == "websocket"
    assert headers["sec-websocket-accept"] == feed.accept_key(key)

    hello = _frame(stream)
    assert json.loads(hello)["type"] == "hello"

    plan(dev)
    change = json.loads(_frame(stream))
    assert change["type"] == "change" and change["verb"] == "plan" and change["seq"] > 0
    sock.close()


def test_a_board_host_serves_no_dashboard_and_names_the_real_window(
    server: BoardServer,
) -> None:
    """`taskops serve` is an events API. Its /ui/ is ONE sentence naming
    `taskops ui`, at 410 — the page was withdrawn on purpose and is not coming
    back to a host that has no clone to read a diff from (`http/static.py`)."""
    assert server.mounts.ui is None and server.mounts.repo is None
    with pytest.raises(HTTPError) as caught:
        urlopen(f"{url_of(server)}/ui/", timeout=5)
    answer = caught.value
    body = answer.read().decode()
    assert answer.code == 410
    assert answer.headers["Content-Type"].startswith("text/plain")
    assert "taskops ui" in body
    # the sentence, and NOT the bundle: no page, no script, no bundle marker.
    assert "<html" not in body.lower() and "<script" not in body.lower()
    assert len(body) < 400


def test_serve_has_no_ui_flag_left_to_configure_a_dashboard_with(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Removed, not left dead: there is no option that puts a bundle back on a
    board host, so the decision cannot be undone by a command line. Read off
    `--help` rather than by feeding `--ui` in: a run that PARSED would go on to
    serve forever, and a test must fail, not hang."""
    from taskops.cli.main import main

    with pytest.raises(SystemExit):
        main(["serve", "--help"])
    printed = capsys.readouterr().out
    assert "--port" in printed and "--ui" not in printed


def test_the_window_still_serves_the_bundle_it_ships_with(
    repo_server: BoardServer,
) -> None:
    """The other half of the same switch: a host that stands in a checkout —
    what `taskops ui` builds — serves the bundle PACKAGED in the wheel. The UI
    was never removed from the package; only the server-side mount was."""
    packaged = Path(str(taskops.__file__)).resolve().parent / "ui"
    assert repo_server.mounts.ui == packaged
    with urlopen(f"{url_of(repo_server)}/ui/", timeout=5) as response:
        body = response.read().decode()
        assert response.headers["Content-Type"].startswith("text/html")
    assert "<script" in body.lower()


# ── plumbing for the raw calls above ────────────────────────────────────────


def _frame(stream: BinaryIO) -> str:
    """Read one server frame, skipping the keep-alive pings. Server frames are
    never masked (RFC 6455 §5.1), so this stays small on purpose."""
    while True:
        first, second = stream.read(2)
        opcode, length = first & 0x0F, second & 0x7F
        if length == 126:
            length = int.from_bytes(stream.read(2), "big")
        elif length == 127:
            length = int.from_bytes(stream.read(8), "big")
        payload = stream.read(length) if length else b""
        if opcode == 0x1:
            return payload.decode()
        if opcode == 0x8:
            raise AssertionError("the server closed the socket")


# ── the /git door: a diff, but only from a host that HAS a repo ─────────────


@pytest.fixture()
def repo_server(tmp_path: Path) -> Iterator[BoardServer]:
    """A host that sits INSIDE a checkout — what `taskops ui` constructs."""
    from tests.test_git import repo

    root = repo(tmp_path, "checkout")
    httpd = serve(tmp_path / "boards", "127.0.0.1", 0, repo=root)
    httpd.mounts.create(BOARD)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def _get(url: str, token: str) -> tuple[int, dict[str, Any]]:
    from urllib.error import HTTPError

    joiner = "&" if "?" in url else "?"
    try:
        with urlopen(f"{url}{joiner}token={token}", timeout=5) as response:
            return response.status, json.loads(response.read().decode())
    except HTTPError as err:
        return err.code, json.loads(err.read().decode())


def test_a_host_with_no_repo_mounts_no_git_and_says_which_case_it_is(
    server: BoardServer,
) -> None:
    """`taskops serve` sits in a boards directory. It refuses and NAMES the
    reason — the UI reads those words and falls through its cascade instead of
    drawing a dead pane. Nothing was ever sniffed: the switch is construction."""
    assert server.mounts.repo is None
    status, body = _get(f"{url_of(server)}/git/commit/HEAD", _token(server, BERNA))
    assert status == 404 and body["ok"] is False
    assert body["error"]["code"] == "not_found"
    assert "not a repository" in body["error"]["message"]
    assert "taskops ui" in body["error"]["message"]


def test_a_repo_host_answers_a_commit_against_its_first_parent(
    repo_server: BoardServer,
) -> None:
    status, body = _get(
        f"{url_of(repo_server)}/git/commit/HEAD", _token(repo_server, BERNA)
    )
    assert status == 200 and body["ok"] is True
    data = body["data"]
    assert data["stat"] == {"README.md": [1, 0]}
    assert "README.md" in data["patch"]
    assert data["truncated"] is False and data["cap"] > 0
    assert len(data["head"]) == 40


def test_the_compare_shape_is_the_same_shape(repo_server: BoardServer) -> None:
    """One vocabulary: a card-as-PR read and a commit read differ in the range,
    never in the payload — the UI has one renderer."""
    status, body = _get(
        f"{url_of(repo_server)}/git/compare/main...main", _token(repo_server, BERNA)
    )
    assert status == 200
    assert set(body["data"]) == {"base", "head", "stat", "patch", "truncated", "cap"}


def test_a_ref_the_repo_lacks_is_a_stated_refusal_never_a_traceback(
    repo_server: BoardServer,
) -> None:
    """It is a REFUSAL, and since the shared-board chapter it is also the right
    one: on a board several clones read, a ref this one lacks is not a broken
    request, it is a fetch nobody has run yet. So the words changed from "this
    repo has no commit X" to the case itself, with the command that clears it —
    the contract this test pins (a stated refusal, never a traceback) did not."""
    status, body = _get(
        f"{url_of(repo_server)}/git/commit/does-not-exist", _token(repo_server, BERNA)
    )
    assert status == 404 and body["ok"] is False
    assert "not in your clone yet" in body["error"]["message"]
    assert "git fetch origin does-not-exist" in body["error"]["message"]
    status, body = _get(
        f"{url_of(repo_server)}/git/nonsense", _token(repo_server, BERNA)
    )
    assert status == 400 and "git/commit/<ref>" in body["error"]["message"]


def test_the_git_door_is_the_same_token_door_as_rpc(repo_server: BoardServer) -> None:
    """No second credential system: no token is refused here exactly as at /rpc."""
    url = f"{url_of(repo_server)}/git/commit/HEAD"
    with pytest.raises(HTTPError) as caught:
        urlopen(url, timeout=5)
    assert json.loads(caught.value.read().decode())["error"]["code"] == "refused"
    status, _ = _get(url, "not-a-real-token")
    assert status in (401, 403, 409)


# ── the WINDOW: a local host serving a remote board ─────────────────────────
#
# Two real servers on two real ports, which is the only way this chapter can be
# proved at all: the bug it exists for was that `taskops ui` opened a page on
# the machine that owns the BOARD, and that machine has no clone. So the fixture
# below is the true topology — a remote host with the board and no repo, and a
# local host with the repo and no board — and every assertion is about which of
# the two answered.


@pytest.fixture()
def window(server: BoardServer, tmp_path: Path) -> Iterator[BoardServer]:
    """`taskops ui` in a checkout joined to `server`. Local UI, local /git,
    forwarded /rpc — built through `serve()` exactly as `cli/serving.py` builds
    it, so nothing here is a shape the command does not use."""
    from tests.test_git import repo
    from taskops.http.upstream import Upstream

    team, _ = server.mounts.credentials.mint(BERNA, BOARD, _clock.now())
    root = repo(tmp_path, "viewer")
    httpd = serve(
        tmp_path / "window",
        "127.0.0.1",
        0,
        repo=root,
        upstream=Upstream(url_of(server), team),
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def _window_token(httpd: BoardServer) -> str:
    """A LOCAL credential for the window's own board name. It is `board` — what
    `cli/serving.py::ui` mounts — and the remote board is called `facturador`,
    which is exactly the point: the page's routes are local and say nothing
    about the server's naming."""
    token, _ = httpd.mounts.credentials.mint(BERNA, "board", _clock.now())
    return token


def _team(httpd: BoardServer) -> str:
    """The credential the window forwards WITH — the one secret this design
    protects. Read off the live Upstream, never a copy kept by the fixture."""
    upstream = httpd.mounts.upstream
    assert upstream is not None
    return upstream.token


def _window_url(httpd: BoardServer) -> str:
    """The window mounts the board under `board`, the name `taskops ui` uses.
    The REMOTE board is called something else entirely (`facturador`) — which is
    the point: the page's routes are local and say nothing about the server."""
    return f"http://127.0.0.1:{httpd.server_address[1]}/board"


def test_the_window_answers_rpc_with_the_REMOTE_boards_data(
    server: BoardServer, window: BoardServer
) -> None:
    """Criterion 1. The cards were planned on the server, over its own port, by
    a client that never touched the window — and the window hands them back."""
    plan(client(server, BERNA))
    token = _window_token(window)
    body = _post(_window_url(window), token, {"verb": "board", "actor": BERNA})

    assert body["ok"] is True and body["seq"] > 0
    assert [c["title"] for c in body["data"]["groups"]["take"]] == ["invoice model", "CSV parser"]
    # And it is not a copy: the window opened NO board of its own on this disk.
    assert not (window.mounts.root / "board").exists()
    assert window.mounts.count() == 0


def test_the_window_writes_through_to_the_remote_board(
    server: BoardServer, window: BoardServer
) -> None:
    """A forwarded write is a real write on the server, not a local one — the
    exact split-brain `board.py` refuses to allow, proved at the other door."""
    cards = plan(client(server, BERNA))
    token = _window_token(window)
    _post(
        _window_url(window),
        token,
        {"verb": "assign", "actor": BERNA, "args": {"tasks": [cards[0]["id"]]}},
    )
    seen = client(server, BERNA).call("card", {"task": cards[0]["id"]})
    assert seen["card"]["assignee"] == W1


def test_the_window_serves_git_from_ITS_OWN_clone(window: BoardServer) -> None:
    """Criterion 2, and the reason the command changed. The remote host has no
    repository at all; this patch came off the viewer's disk."""
    status, body = _get(f"{_window_url(window)}/git/commit/HEAD", _window_token(window))
    assert status == 200 and body["ok"] is True
    assert body["data"]["stat"] == {"README.md": [1, 0]}
    assert "README.md" in body["data"]["patch"]


def test_a_branch_this_clone_has_not_fetched_reads_as_itself(window: BoardServer) -> None:
    """Criterion 3. Another dev's card closed and pushed; this clone has not
    fetched. That is a fact about this disk, not a failure, and the answer names
    the command that clears it — it does NOT fetch on the reader's behalf."""
    status, body = _get(
        f"{_window_url(window)}/git/compare/main...tk-91a27e", _window_token(window)
    )
    assert status == 404 and body["error"]["code"] == "not_found"
    assert "tk-91a27e is not in your clone yet" in body["error"]["message"]
    assert "git fetch origin tk-91a27e" in body["error"]["message"]
    assert "main" not in body["error"]["message"].partition("The board is shared")[0]


def test_a_refusal_from_the_remote_arrives_in_the_servers_own_words(
    server: BoardServer, window: BoardServer
) -> None:
    """Criterion 4. The role wall lives on the server; through the window it must
    still be the SERVER's sentence and the SERVER's status. A local 500 with a
    traceback would have the reader debugging the wrong machine."""
    cards = plan(client(server, BERNA))
    status, body = _get_post(
        _window_url(window),
        _window_token(window),
        {"verb": "take", "actor": BERNA, "args": {"task": cards[0]["id"]}},
    )
    assert status == 409 and body["ok"] is False
    assert body["error"]["code"] == "refused"
    assert "taskops_assign" in body["error"]["message"]


def test_the_remote_credential_never_reaches_the_browser(
    server: BoardServer, window: BoardServer
) -> None:
    """Criterion 5, and the reason forwarding beat pointing the page at the
    remote. The team's bearer is the one secret this whole design protects, so
    it is searched for in every byte the window serves: the answers, their
    HEADERS, and the page's own token file."""
    plan(client(server, BERNA))
    team = _team(window)
    local = _window_token(window)
    assert team != local

    seen: list[str] = []
    request = Request(
        f"{_window_url(window)}/rpc",
        data=json.dumps({"verb": "board", "actor": BERNA}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {local}"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        seen.append(response.read().decode())
        seen.append(str(response.headers))
    status, refused = _get(f"{_window_url(window)}/git/commit/nope", local)
    seen.append(json.dumps(refused))
    assert status == 404
    assert all(team not in byte for byte in seen), "the team credential left this process"


def test_the_window_pokes_the_page_when_the_REMOTE_board_moves(
    server: BoardServer, window: BoardServer
) -> None:
    """Criterion 6. No WebSocket is relayed and no SSE is proxied: the local host
    polls the remote's `seq` and pokes the socket it already serves. The write
    below goes to the SERVER, on its own port, so the only way this stream can
    learn about it is the poll."""
    stream = urlopen(f"{_window_url(window)}/feed?token={_window_token(window)}", timeout=20)
    assert b"hello" in stream.readline() + stream.readline()

    # Wait for two keep-alive pings BEFORE writing. The watcher takes its
    # baseline `seq` on the way in, so a write that lands in that same instant
    # is already in the baseline and there is nothing left to notice — a race
    # in the test, not in the product, and one this file would otherwise fail
    # on about half the time. Two pings is four seconds, past one 3s poll.
    for _ in range(2):
        while not stream.readline().startswith(b":"):
            pass

    plan(client(server, BERNA))  # not through the window

    seen: dict[str, Any] = {}
    for _ in range(12):  # bounded by LINES: this suite freezes the clock
        line = stream.readline().decode().strip()
        if line.startswith("data:"):
            payload: Any = json.loads(line[5:])
            if payload.get("type") == "change":
                seen = payload
                break
    assert seen.get("seq", 0) > 0, "the remote board moved and the page was never told"
    stream.close()


def test_a_repo_joined_to_nothing_still_serves_its_own_board(repo_server: BoardServer) -> None:
    """Criterion 7. No upstream, no forward: the same host, answering itself,
    exactly as it did before this chapter."""
    assert repo_server.mounts.upstream is None
    dev = RemoteBoard(url_of(repo_server), _token(repo_server, BERNA), BERNA)
    dev.call("plan", {"milestone": "M", "goal": "g", "tasks": [{"title": "local"}]})
    assert [c["title"] for c in dev.call("board", {})["groups"]["take"]] == ["local"]


def test_a_window_whose_server_is_gone_says_so_and_writes_nothing(
    server: BoardServer, window: BoardServer
) -> None:
    """The only answer the forward writes itself. It never falls back to a local
    store — that is v1's split brain, refused here as it is in `board.py`."""
    server.shutdown()
    server.server_close()
    status, body = _get_post(
        _window_url(window), _window_token(window), {"verb": "board", "actor": BERNA}
    )
    assert status == 502 and body["error"]["code"] == "unreachable"
    assert "nothing was written" in body["error"]["message"]
    assert not (window.mounts.root / "board").exists()


def test_the_command_reads_the_mode_off_the_config_and_nothing_else(tmp_path: Path) -> None:
    """The whole switch, at the only place it is decided."""
    from taskops.cli import serving

    root = tmp_path / "checkout"
    (root / ".taskops").mkdir(parents=True)
    (root / ".taskops" / "board.json").write_text("{}", encoding="utf-8")
    assert serving._upstream(root) is None  # noqa: SLF001 — the decision under test

    (root / ".taskops" / "board.json").write_text(
        json.dumps({"url": "https://boards.example/facturador"}), encoding="utf-8"
    )
    with pytest.raises(TaskopsError, match="taskops join"):
        serving._upstream(root)  # noqa: SLF001 — an address with no credential

    (root / ".taskops" / "remote.json").write_text(
        json.dumps({"token": "t0ken"}), encoding="utf-8"
    )
    upstream = serving._upstream(root)  # noqa: SLF001
    assert upstream is not None
    assert upstream.url == "https://boards.example/facturador" and upstream.token == "t0ken"


def test_the_command_itself_serves_the_window(
    server: BoardServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`taskops ui`, run for real, against a checkout joined to `server`.

    MEASURED, and the reason this test exists rather than one more assertion on
    `_upstream`: deleting `upstream=upstream` from the command's own
    `make_server` call left the entire suite green. Every other test here builds
    its window through `serve()` the way the command does, which proves the
    server and proves nothing about the WIRING between the decision and it. So
    this one runs the command — its `find_root`, its config read, its minted
    token, its `ui.json` — and reads the answer off the port it chose."""
    from taskops.cli import serving
    from tests.test_git import repo

    plan(client(server, BERNA))
    root = repo(tmp_path, "viewer")  # a real clone: /git must come out of THIS one
    (root / ".taskops").mkdir(parents=True)
    (root / ".taskops" / "board.json").write_text(
        json.dumps({"url": url_of(server)}), encoding="utf-8"
    )
    (root / ".taskops" / "remote.json").write_text(
        json.dumps({"token": _token(server, BERNA)}), encoding="utf-8"
    )
    monkeypatch.setattr(serving.webbrowser, "open", lambda _url: True)

    threading.Thread(target=serving.ui, args=(root,), daemon=True).start()
    state = root / ".taskops" / "ui.json"
    for _ in range(200):  # the command writes it right after it binds
        if state.exists():
            break
        threading.Event().wait(0.05)
    assert state.exists(), "taskops ui never bound a port"
    window: dict[str, Any] = json.loads(state.read_text())

    base = f"http://127.0.0.1:{window['port']}/board"
    body = _post(base, str(window["token"]), {"verb": "board", "actor": BERNA})
    assert [c["title"] for c in body["data"]["groups"]["take"]] == ["invoice model", "CSV parser"]
    # ...and the SAME command mounted /git from the checkout it was run in.
    status, patch = _get(f"{base}/git/commit/HEAD", str(window["token"]))
    assert status == 200 and patch["data"]["stat"] == {"README.md": [1, 0]}
    assert not (root / ".taskops" / "board").exists()  # no second, empty board here


def test_a_directory_with_no_board_is_refused_exactly_as_before(tmp_path: Path) -> None:
    """Criterion 7's other half: nothing about this chapter reached a repo that
    joined nothing. It is still the same sentence naming the same two commands."""
    from taskops.cli import serving

    with pytest.raises(TaskopsError, match="taskops init starts one"):
        serving.ui(tmp_path)


def _get_post(url: str, token: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """`_post` raises on a non-200; a refusal is exactly what several of the
    tests above are reading, status and all."""
    request = Request(
        f"{url}/rpc",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            return int(response.status), json.loads(response.read().decode())
    except HTTPError as err:
        return int(err.code), json.loads(err.read().decode())


def _token(httpd: BoardServer, subject: str) -> str:
    token, _ = httpd.mounts.credentials.mint(subject, BOARD, _clock.now())
    return token


def _post(url: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
    from urllib.request import Request

    request = Request(
        f"{url}/rpc",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        body: dict[str, Any] = json.loads(response.read().decode())
    return body


def _redeem(url: str, invite: str, who: str) -> dict[str, Any]:
    from urllib.error import HTTPError
    from urllib.request import Request

    request = Request(
        f"{url}/invite/redeem",
        data=json.dumps({"invite": invite, "who": who}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            body: dict[str, Any] = json.loads(response.read().decode())
    except HTTPError as err:
        body = json.loads(err.read().decode())
    if not body.get("ok"):
        raise Refused(str(body["error"]["message"]))
    data: dict[str, Any] = body["data"]
    return data


_ = T0


# ── review, across the wire ─────────────────────────────────────────────────

R1 = "agent:berna/r1"
R2 = "agent:berna/r2"


def reviewed(board: RemoteBoard) -> str:
    """One card that requires review, taken and handed in — over the wire."""
    cards = board.call(
        "plan",
        {
            "milestone": "MVP facturador",
            "goal": "read a bank CSV and issue invoices with VAT",
            "reviews": True,
            "tasks": [{"title": "invoice model", "spec": "the Invoice dataclass"}],
        },
    )["cards"]
    return str(cards[0]["id"])


def handed_in(server: BoardServer) -> str:
    dev = client(server, BERNA)
    worker = client(server, W1, subject=BERNA)
    card = reviewed(dev)
    worker.call("take", {"task": card})
    worker.call("bind", {"task": card, "sha": "a1b2", "subject": "feat: model"})
    worker.call("update", {"task": card, "status": "review", "comment": "model + tests"})
    return card


def test_two_remote_verifiers_race_and_only_one_claims(server: BoardServer) -> None:
    """Berna's question: two verifiers spawned at once, over the network.

    There is no second arbiter to disagree with — every client talks to ONE
    server process holding ONE file, and the claim is an INSERT on a primary
    key. One row, one winner, and the loser is told who won.
    """
    card = handed_in(server)
    first = client(server, R1, subject=BERNA)
    second = client(server, R2, subject=BERNA)

    assert first.call("review", {"task": card})["card"]["id"] == card
    with pytest.raises(Refused, match="already being reviewed by agent:berna/r1"):
        second.call("review", {"task": card})

    dev = client(server, BERNA)
    assert [r["id"] for r in dev.call("board", {})["groups"]["reviewing"]] == [card]


def test_two_conflicting_verdicts_leave_the_board_coherent(server: BoardServer) -> None:
    """§3.2 race 2 — 'the atomic somehow does not save you'.

    A verdict is an APPENDED event, never a mutated field, so there is no cell
    for two writers to interleave on. Both land in the thread and the board
    stays readable. What `standing` answers is the LAST verdict of the current
    round: a `pass` followed by a `changes` reads as `changes`, and the close
    guard still refuses — a human is shown the whole thread and decides.
    """
    card = handed_in(server)
    first = client(server, R1, subject=BERNA)
    second = client(server, R2, subject=BERNA)
    dev = client(server, BERNA)

    first.call("review", {"task": card, "verdict": "pass", "note": "rounding checked"})
    second.call("review", {"task": card, "verdict": "changes", "note": "_total() is float"})

    full = dev.call("card", {"task": card})
    verdicts = [e["body"]["verdict"] for e in full["history"] if e["kind"] == "reviewed"]
    assert verdicts == ["pass", "changes"]  # both are on the record, neither is lost
    assert full["card"]["status"] == "open"
    assert full["standing"]["verdict"] == "changes"
    worker = client(server, W1, subject=BERNA)
    with pytest.raises(Refused, match="needs a passing review"):
        worker.call("update", {"task": card, "status": "done", "comment": "call it"})
    # the orchestrator's exception (§6.3) is narrow on purpose — it only opens
    # for a `pass`, so a disagreement leaves it on the outside of the same wall
    # as everybody else, with the whole thread in front of it.
    with pytest.raises(Refused, match="held by agent:berna/w1"):
        dev.call("update", {"task": card, "status": "done", "comment": "call it"})
