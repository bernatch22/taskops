"""THE seam test: a real HTTP server on a real port, two real clients.

Every bug worth its own test in v1 lived between two machines — twelve in three
days, all invisible to tests that used a single store. So this file never uses
`Stores` directly: it talks to `RemoteBoard`, over a socket, like an agent does.
"""

from __future__ import annotations

import os
import json
import socket
import argparse
import threading
import subprocess
from base64 import b64encode
from typing import Any, BinaryIO, Iterator
from hashlib import sha256
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

import taskops
from taskops import _clock
from taskops.http import feed
from taskops.board import RemoteBoard
from tests.conftest import T0
from taskops._errors import Refused, NotFound, BadRequest, Unreachable, TaskopsError
from taskops._locate import read_config
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


# ── a key signs you in: the login that mints the session ────────────────────
#
# Nothing here is a fake: a REAL keypair is generated by ssh-keygen into the
# test's tmp_path, a REAL signature crosses a REAL socket, and the server
# verifies it by running `ssh-keygen -Y verify` against the `allowed_signers`
# its own store regenerated. A stub of the signature would test the plumbing
# and nothing that matters — the whole claim of this chapter is that OpenSSH,
# not taskops, decides whether a signature is good.


def keygen(path: Path) -> Path:
    """A throwaway ed25519 keypair, made the way a human makes one."""
    from taskops.gitwork.run import tool

    made = tool("ssh-keygen", "-t", "ed25519", "-N", "", "-C", "probe", "-q", "-f", str(path))
    if not made.ok:  # pragma: no cover — a machine without OpenSSH
        raise AssertionError(f"ssh-keygen could not make a key: {made.err or made.out}")
    return path


@pytest.fixture()
def keyed(server: BoardServer, tmp_path: Path) -> Path:
    """The server above, bootstrapped with berna as OWNER of a real key."""
    from taskops.cli import admin

    key = keygen(tmp_path / "id_ed25519")
    admin.init(tmp_path / "boards", f"{key}.pub", "berna")
    return key


def sign_in(httpd: BoardServer, principal: str, key: Path) -> dict[str, Any]:
    """The client's two round trips: ask for a challenge, sign it, hand it back."""
    opened = challenge(httpd, principal)
    return answer_with(httpd, principal, opened["nonce"], signed(principal, opened["nonce"], key))


def host_of(httpd: BoardServer) -> str:
    """The SERVER, not a board: /login is server scope and takes no board name."""
    return f"http://127.0.0.1:{httpd.server_address[1]}"


def challenge(httpd: BoardServer, principal: str) -> dict[str, Any]:
    from taskops import _wire

    return _wire.post(f"{host_of(httpd)}/login", {"principal": principal}, {}, 5.0)


def answer_with(httpd: BoardServer, principal: str, nonce: str, signature: str) -> dict[str, Any]:
    from taskops import _wire

    return _wire.post(
        f"{host_of(httpd)}/login",
        {"principal": principal, "nonce": nonce, "signature": signature},
        {},
        5.0,
    )


def signed(principal: str, nonce: str, key: Path) -> str:
    from taskops.gitwork.sig import sign
    from taskops.core.challenge import payload

    return sign(payload(principal, nonce), key)


def test_a_registered_key_signs_in_and_the_minted_token_works_on_rpc(
    server: BoardServer, keyed: Path, clock: Any
) -> None:
    """Criterion 1, end to end and over a socket: challenge → ssh-keygen -Y sign →
    verify against allowed_signers → a bearer token that /rpc already understood."""
    opened = challenge(server, "berna")
    assert opened["namespace"] == "taskops"
    assert opened["expires"] == _clock.now() + 120.0
    assert "token" not in opened  # a challenge is not a credential

    minted = answer_with(server, "berna", opened["nonce"], signed("berna", opened["nonce"], keyed))
    assert minted["actor"] == "dev:berna"
    assert minted["role"] == "owner"
    assert minted["expires"] == _clock.now() + 12 * 3600.0

    # The whole point: NOTHING downstream changed. The token is an ordinary
    # bearer on the ordinary door, for a board it was never told the name of.
    board = RemoteBoard(url_of(server), minted["token"], BERNA)
    assert board.call("board", {})["seq"] >= 0

    # And it is SHORT-lived for real, not just in the number it reported: the
    # credential itself carries the TTL, so a day later this token is nobody's.
    clock(12 * 3600.0 + 1.0)
    with pytest.raises(Refused, match="that credential expired"):
        board.call("board", {})


def test_a_challenge_is_single_use_and_dies_of_old_age(
    server: BoardServer, keyed: Path, clock: Any
) -> None:
    """Criterion 2, both halves. There is no replay window to reason about
    because the nonce is gone the instant it is claimed."""
    opened = challenge(server, "berna")
    signature = signed("berna", opened["nonce"], keyed)
    answer_with(server, "berna", opened["nonce"], signature)  # the first one works
    with pytest.raises(Refused, match="unknown or already used"):
        answer_with(server, "berna", opened["nonce"], signature)

    stale = challenge(server, "berna")
    signature = signed("berna", stale["nonce"], keyed)
    clock(121.0)
    with pytest.raises(Refused, match="expired"):
        answer_with(server, "berna", stale["nonce"], signature)


def test_a_signature_by_a_key_this_host_never_registered_is_refused(
    server: BoardServer, keyed: Path, tmp_path: Path
) -> None:
    """The signature is checked by ssh-keygen against allowed_signers, so a
    well-formed signature by a stranger's key is exactly as good as no key."""
    mallory = keygen(tmp_path / "mallory")
    opened = challenge(server, "berna")
    with pytest.raises(Refused, match="not berna's"):
        answer_with(server, "berna", opened["nonce"], signed("berna", opened["nonce"], mallory))

    # ...and neither is a signature over somebody ELSE's challenge.
    hers = challenge(server, "berna")
    with pytest.raises(Refused, match="not berna's"):
        answer_with(server, "berna", hers["nonce"], signed("berna", "a-different-nonce", keyed))


def test_a_nonce_issued_to_somebody_else_is_refused_by_NAME(
    server: BoardServer, keyed: Path, tmp_path: Path
) -> None:
    """A challenge belongs to the principal it was issued to, and the refusal says
    WHOSE it was. ssh-keygen would refuse this too — its `-I` check does not care
    what the payload says — but it would refuse it as 'that signature is not
    berna's', which sends a confused client looking at its key instead of at the
    nonce it mixed up. The invariant is checked where it can be named.
    """
    from taskops.store.server import ServerStore

    store = ServerStore(tmp_path / "boards")
    try:
        pub = Path(f"{keygen(tmp_path / 'ana')}.pub").read_text(encoding="utf-8")
        store.enroll("ana", "member", pub, _clock.now())
    finally:
        store.close()

    hers = challenge(server, "ana")
    with pytest.raises(Refused, match="issued to 'ana'"):
        answer_with(server, "berna", hers["nonce"], signed("berna", hers["nonce"], keyed))


def test_an_unregistered_principal_never_even_gets_a_challenge(
    server: BoardServer, keyed: Path
) -> None:
    """Criterion 4's other half and the milestone's house rule: the refusal to an
    unkeyed caller says how a key gets registered."""
    with pytest.raises(Refused) as caught:
        challenge(server, "mallory")
    assert "anon may not session.mint" in str(caught.value)
    assert "taskops server key add" in str(caught.value)


def test_a_host_nobody_bootstrapped_refuses_a_login_and_writes_nothing(
    server: BoardServer, tmp_path: Path
) -> None:
    """The milestone's second rule at the newest door: an anonymous caller may
    not cause a write, and `ServerStore` writes on CONSTRUCTION — so the login
    must refuse BEFORE one is built."""
    root = tmp_path / "boards"
    with pytest.raises(TaskopsError, match="taskops server init"):
        challenge(server, "berna")
    assert not (root / "server.sqlite").exists()
    assert not (root / "allowed_signers").exists()


def test_the_agent_only_limit_is_one_sentence_and_not_a_traceback(tmp_path: Path) -> None:
    """Criterion 4. `ssh-keygen -Y sign` wants the key FILE; a key that lives only
    in a running ssh-agent cannot sign yet, and saying so is the whole fix."""
    from taskops.gitwork.sig import sign

    with pytest.raises(Refused) as caught:
        sign("anything", tmp_path / "not-on-disk")
    assert "needs the key ON DISK" in str(caught.value)
    assert "agent-only setup" in str(caught.value)


def test_an_expired_session_signs_itself_in_again_with_no_human(
    server: BoardServer, keyed: Path, tmp_path: Path, clock: Any
) -> None:
    """Criterion 3, through `open_board` — which is every CLI invocation."""
    from typing import cast

    from taskops import session
    from taskops.board import RemoteBoard as Remote, open_board
    from taskops.gitwork import install

    project = tmp_path / "clone"
    door = {"host": host_of(server), "principal": "berna", "key": str(keyed)}
    install.write_config(project, url_of(server), "", door, 0.0)

    first = cast("Remote", open_board(project, BERNA))  # no token at all: it mints one
    assert first.token
    assert first.call("board", {})["seq"] >= 0
    cached = json.loads((project / ".taskops" / "remote.json").read_text())
    assert cached["token"] == first.token
    assert cached["token_expires"] == _clock.now() + 12 * 3600.0
    assert cached["login"] == door  # the refresh survives its own rewrite

    clock(12 * 3600.0)  # a day later, the session is spent
    again = cast("Remote", open_board(project, BERNA))
    assert again.token != first.token
    assert again.call("board", {})["seq"] >= 0

    # A session about to run out is replaced BEFORE it can die mid-call: a token
    # that expires between the check and the call it authorises would be a bug
    # reproducing once a day, which is the worst reproduction rate there is.
    nearly = {"token": "old", "token_expires": _clock.now() + 60.0, "login": door}
    assert session.fresh(project, nearly, _clock.now()) != "old"

    # And the case `open_board` cannot cover: a process that outlives its own
    # token. The MCP server opens a board once and keeps it for the session.
    live = session.fresh(project, {"token": "", "login": door}, _clock.now())
    stale, _ = server.mounts.credentials.mint(BERNA, "*", _clock.now() - 10.0, ttl=1.0)
    board = Remote(url_of(server), stale, BERNA, refresh=session.refresher(project, {"login": door}))
    assert board.call("board", {})["seq"] >= 0  # refused, refreshed, retried
    assert board.token not in ("", stale, live)


def test_a_standing_bearer_token_is_never_replaced_behind_its_owners_back(
    server: BoardServer, tmp_path: Path
) -> None:
    """Criterion 5. Production has four boards joined the old way; a config with
    no `login` block is one of them, and this file is what it looks like."""
    from typing import cast

    from taskops.board import RemoteBoard as Remote, open_board
    from taskops.gitwork import install

    project = tmp_path / "legacy"
    token = _token(server, BERNA)
    install.write_config(project, url_of(server), token)
    assert json.loads((project / ".taskops" / "remote.json").read_text()) == {"token": token}

    board = cast("Remote", open_board(project, BERNA))
    assert board.token == token
    assert board.refresh is None  # nothing to refresh WITH, so nothing is attempted
    assert board.call("board", {})["seq"] >= 0


def test_a_login_block_still_never_touches_a_STANDING_token(
    server: BoardServer, keyed: Path, tmp_path: Path
) -> None:
    """The other side of the same rule, and the one a hand-written config can hit:
    a token with no expiry is somebody's decision, not a stale session, and a key
    sitting next to it in the file is not permission to replace it."""
    from taskops import session

    door = {"host": host_of(server), "principal": "berna", "key": str(keyed)}
    kept = session.fresh(tmp_path / "clone", {"token": "standing", "login": door}, _clock.now())
    assert kept == "standing"


def test_join_with_a_key_leaves_a_SESSION_behind_and_not_the_invites_token(
    server: BoardServer, keyed: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`taskops join --key`, the whole command. The invite's token is a STANDING
    one; a clone that kept it would never take the refresh path again, so the key
    signs in during the join and what lands in remote.json is a session."""
    from taskops.cli import commands

    invite, _ = server.mounts.credentials.mint(
        "invite:ana", BOARD, _clock.now(), caps="read,write", once=True
    )
    hers = keygen(tmp_path / "ana_id")
    project = tmp_path / "hers"
    (project / ".git").mkdir(parents=True)
    monkeypatch.setenv("TASKOPS_ACTOR", "dev:ana")
    commands.join(project, f"{url_of(server)}?invite={invite}", "dev:ana", str(hers))

    saved = json.loads((project / ".taskops" / "remote.json").read_text())
    assert saved["login"] == {"host": host_of(server), "principal": "ana", "key": str(hers)}
    assert saved["token_expires"] == _clock.now() + 12 * 3600.0  # a session, not the invite's
    assert RemoteBoard(url_of(server), saved["token"], ANA).call("board", {})["seq"] >= 0


def test_an_invite_registers_the_joiners_key_and_still_answers_a_token(
    server: BoardServer, keyed: Path, tmp_path: Path
) -> None:
    """Criterion 5's other half: the legacy answer is UNCHANGED and the pubkey is
    the new half of the same call — one act, so a joiner never copies a token."""
    from taskops.store.server import ServerStore

    invite, _ = server.mounts.credentials.mint(
        "invite:ana", BOARD, _clock.now(), caps="read,write", once=True
    )
    hers = keygen(tmp_path / "ana_key")
    got = _redeem(url_of(server), invite, "ana", f"{hers}.pub")
    assert got["actor"] == "dev:ana"  # the shape the old flow answered, untouched
    RemoteBoard(url_of(server), got["token"], ANA).call("board", {})

    store = ServerStore(tmp_path / "boards")
    try:
        assert store.role_of("ana") == "member"
        assert store.role_of("berna") == "owner"  # the owner did not become a member
    finally:
        store.close()
    minted = sign_in(server, "ana", hers)  # and her key signs her in from now on
    assert RemoteBoard(url_of(server), minted["token"], ANA).call("board", {})["seq"] >= 0


def test_a_clone_that_carries_its_boards_address_joins_bare_no_url_no_remote(
    server: BoardServer, keyed: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """v1's two-word join, restored (2026-08-11). `.taskops/board.json` is
    COMMITTED and travels with the clone, so the second developer types
    `taskops join` and nothing else — no URL pasted from a chat, no
    `remote add` first. The regression: v2 resolved a bare join through the
    RECORDED remote (`remote.json`, per-machine, never travels) and ignored the
    address the clone already carried. The recorded remote stays the fallback
    for a checkout with no carried address, or a join onto a DIFFERENT board.

    Both bare spellings, because both read the carried address: no target at
    all, and the board's own name (which must not fall through to `named()`
    and die on the missing remote)."""
    from taskops.cli import commands

    for target in ("", BOARD):
        project = tmp_path / f"clone-{target or 'bare'}"
        (project / ".git").mkdir(parents=True)
        (project / ".taskops").mkdir()
        (project / ".taskops" / "board.json").write_text(json.dumps({"url": url_of(server)}))
        monkeypatch.setenv("TASKOPS_ACTOR", BERNA)
        commands.join(project, target, BERNA, str(keyed))
        saved = json.loads((project / ".taskops" / "remote.json").read_text())
        assert saved["login"]["host"] == host_of(server)
        assert RemoteBoard(url_of(server), saved["token"], BERNA).call("board", {})["seq"] >= 0


def test_a_re_join_never_demotes_the_owner_it_only_adds_a_key(
    server: BoardServer, keyed: Path, tmp_path: Path
) -> None:
    """`ServerStore.enroll` is an INSERT OR REPLACE on principals, so calling it
    for a name this host already knows would rewrite that principal's ROLE — the
    owner re-joining with an invite would silently demote itself to member."""
    from taskops.store.server import ServerStore

    invite, _ = server.mounts.credentials.mint(
        "invite:berna", BOARD, _clock.now(), caps="read,write", once=True
    )
    second = keygen(tmp_path / "berna_laptop")
    _redeem(url_of(server), invite, "berna", f"{second}.pub")

    store = ServerStore(tmp_path / "boards")
    try:
        assert store.role_of("berna") == "owner"
        assert len(store.keys("berna")) == 2  # both keys, one principal
    finally:
        store.close()
    assert sign_in(server, "berna", second)["token"]  # the new key signs in too


# ── the GitHub introduction the DEV used to carry (deleted 2026-08-11) ───────
#
# A board door lived here: a dev posted their OWN GitHub token and the host asked
# GitHub whether it had `need` on the declared repo. Six tests
# pinned it — the enrolment, the token in no file, the three refusals by name, an
# unreachable GitHub never degrading into a yes, the invite-only board with no
# forge, and membership not being permission to BE somebody. They are deleted
# rather than adapted because the CONTRACT they pinned is the one this chapter
# retires: nobody proves their membership at the host's door any more. The owner
# already knows who works on the repo, so `taskops board forge` enrols the whole
# team from their laptop and no dev's token travels at all — every one of those
# six guarantees now holds by there being nothing to guard. The sync's own tests
# are the tail block at the end of this file, and the dev's side is the plain
# `taskops join` in `test_the_dev_whose_key_the_sync_published_joins_with_two_words`.
#
# What survives here is the token STRING: the tail block greps for it, and a
# forge sync must be as unable to write it to disk as that door was.

TOKEN = "ghp_a-token-that-must-never-land-on-disk"


# ── `taskops board forge`: the door onto the opt-in ──────────────────────────
#
# The chapter's opt-in existed with no human-facing surface: `op=forge` was
# reachable from a raw /rpc call and nowhere else, so the only board that could
# ever be opted in was one whose owner hand-wrote JSON. These pin the CLI half.
#
# A third test stood here and is deleted with the door it guarded: it TYPED the
# board door's own refusal sentence as argv, so the message naming
# `taskops board forge` and the command answering it could not drift. The
# sentence, the constant holding it and the door that raised it are all gone —
# there is no refusal to keep in step with any more, and the two below already
# run the command it named.


def test_the_forge_is_cleared_back_to_invite_only_by_the_same_verb(
    server: BoardServer, keyed: Path, virgin: Path, hub: Hub
) -> None:
    """Opting in is reversible or it is a trap. `--clear` is a FLAG and not the
    word "none", so no repository can ever be named the thing that undoes it.
    Declared, read back, cleared, read back — through the CLI, against a server.

    And clearing asks GitHub NOTHING: the sync runs on the fact re-read out of
    the answer (`cli/operate.py::_forge`), so an empty fact is a board that has
    stopped talking to a forge rather than one syncing an empty team over it."""
    from taskops.cli import main
    from taskops.verbs.project import forge as declared

    at = f"{host_of(server)}/{BOARD}"
    key = ["--key", str(keyed)]
    assert main(["board", "forge", at, "bernatch22/taskops", "--need", "admin", *key]) == 0
    assert declared(server.mounts.stores(BOARD)) == {
        "host": "github.com",
        "repo": "bernatch22/taskops",
        "need": "admin",
    }
    asked = len(hub.seen)
    assert asked  # the declaration DID sync — that is the other half of the verb

    assert main(["board", "forge", at, "--clear", *key]) == 0
    assert declared(server.mounts.stores(BOARD)) is None
    assert len(hub.seen) == asked  # cleared means nothing leaves this host again


def test_the_bare_form_reads_its_one_positional_as_the_repo_not_the_board(
    server: BoardServer, keyed: Path, virgin: Path, hub: Hub, capsys: pytest.CaptureFixture[str]
) -> None:
    """The form the refusal prints and the README documents: ONE argument, and
    it is the REPO — the board is the recorded one, as with every other bare
    verb. argparse fills positionals left to right and cannot know that, so
    without the swap in `operate._forge` this asks for a board called
    `bernatch22/taskops`; `board visibility` carries the same amendment."""
    from taskops.cli import main
    from taskops.verbs.project import forge as declared

    assert main(["board", "create", f"{host_of(server)}/e2e", "--key", str(keyed)]) == 0
    capsys.readouterr()
    assert main(["board", "forge", "bernatch22/taskops"]) == 0  # no host, no key, no board
    printed = capsys.readouterr().out
    # Neither `github.com` nor `push` was typed: the CLI sends `need=""` and the
    # forge host not at all, and what it PRINTS is the fact the server decided
    # and re-read — a command that echoed its own argv would agree with itself
    # while the board said something else.
    assert "e2e on http" in printed and "opened by github.com/bernatch22/taskops" in printed
    assert "everyone with push on it is enrolled below; they join with: taskops join" in printed
    assert declared(server.mounts.stores("e2e")) == {
        "host": "github.com",
        "repo": "bernatch22/taskops",
        "need": "push",
    }
    assert not (server.mounts.root / "bernatch22").exists()


def test_declaring_a_forge_is_the_owners_move_and_a_typo_is_refused_by_name(
    server: BoardServer, keyed: Path, virgin: Path, tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`board.visibility`'s wall, one notch sharper: a member holds a key to the
    board, and this fact decides who ELSE gets one. And the CLI does not own the
    vocabulary — `core/forge.py::declare` refuses loudly, which is what a door a
    human types at wants; the board keeps no half-declared fact either way."""
    from taskops.cli import main
    from taskops.verbs.project import forge as declared

    at = f"{host_of(server)}/{BOARD}"
    key = ["--key", str(keyed)]
    assert main(["board", "forge", at, "bernatch22/taskops/extra", *key]) == 1
    assert "exactly owner/name" in capsys.readouterr().err
    assert main(["board", "forge", *key]) == 1  # neither a repo nor --clear
    assert "--clear" in capsys.readouterr().err
    assert declared(server.mounts.stores(BOARD)) is None

    hers, _ = member(server, tmp_path)
    with pytest.raises(Refused, match="OWNER's move"):
        admin(server, hers, "board.forge", {"board": BOARD, "repo": "x/y", "need": "push"})
    assert declared(server.mounts.stores(BOARD)) is None


# ── the host is operated from taskops, over its own API ─────────────────────
#
# The anomaly the whole chapter exists to kill: every admin act used to be an
# ssh session. These run against the SAME real server and the SAME real keypair
# as the login tests above — an owner, a member, and a socket between them.


def admin(httpd: BoardServer, token: str, verb: str, args: dict[str, Any]) -> dict[str, Any]:
    """The root /rpc — the server's OWN door, one segment, no board name."""
    from taskops import _wire

    return _wire.post(
        f"{host_of(httpd)}/rpc",
        {"verb": verb, "args": args},
        {"Authorization": f"Bearer {token}"},
        5.0,
    )


@pytest.fixture()
def owner(server: BoardServer, keyed: Path) -> str:
    """berna's SESSION token, minted by his key exactly as the CLI mints it."""
    return str(sign_in(server, "berna", keyed)["token"])


def member(server: BoardServer, tmp_path: Path, name: str = "ana") -> tuple[str, Path]:
    """A second principal, enrolled the way a real join enrols one: an invite
    redeemed with a pubkey. No fixture writes to the store behind the server."""
    invite, _ = server.mounts.credentials.mint(f"invite:{name}", BOARD, _clock.now(), once=True)
    hers = keygen(tmp_path / f"{name}_key")
    _redeem(url_of(server), invite, name, f"{hers}.pub")
    return str(sign_in(server, name, hers)["token"]), hers


def test_the_owner_creates_a_board_from_the_laptop_and_the_creator_is_recorded(
    server: BoardServer, owner: str
) -> None:
    """Criterion 1, over a socket with a real signature behind the token: the board
    exists on the server, it answers /rpc, and it carries WHO made it — the one
    fact about a board no later event could reconstruct."""
    made = admin(server, owner, "board.create", {"name": "nuevo"})
    assert made["board"] == "nuevo" and made["created_by"] == BERNA
    assert (server.mounts.root / "nuevo").is_dir()

    token, _ = server.mounts.credentials.mint(BERNA, "nuevo", _clock.now())
    fresh = RemoteBoard(f"http://127.0.0.1:{server.server_address[1]}/nuevo", token, BERNA)
    assert fresh.call("board", {})["seq"] >= 1
    assert server.mounts.stores("nuevo").state()["project"]["created"] == {"by": BERNA}


def test_creating_a_board_that_exists_is_refused_and_never_answers_ok(
    server: BoardServer, owner: str
) -> None:
    """`Mounts.create` is mkdir(exist_ok=True), so without the refusal "creating"
    a live board would answer ok and hand its history back as if it were new."""
    with pytest.raises(Refused, match="already has a board"):
        admin(server, owner, "board.create", {"name": BOARD})
    # The name wall runs BEFORE the existence check, and that order is the test:
    # `../boards` IS a directory, so with the two swapped the answer would be
    # "this host already has a board named '../boards'" — a refusal that is
    # wrong AND leaks that something outside the root exists.
    for escape in ("../escape", f"../{server.mounts.root.name}"):
        with pytest.raises(BadRequest, match="names are"):
            admin(server, owner, "board.create", {"name": escape})
    assert not (server.mounts.root.parent / "escape").exists()


def test_a_member_calling_an_owner_verb_is_refused_BY_ROLE(
    server: BoardServer, owner: str, tmp_path: Path
) -> None:
    """Criterion 2. The refusal names the role that may — and it comes from
    `core/scope.py::permit`, the same gate `session.mint` goes through, so the
    rule cannot be re-taken differently at a second call site."""
    hers, _ = member(server, tmp_path)
    with pytest.raises(Refused) as refused:
        admin(server, hers, "board.create", {"name": "suyo"})
    assert "member may not board.create" in str(refused.value)
    assert "owner may" in str(refused.value)
    assert not (server.mounts.root / "suyo").exists()

    for verb, args in (("invite.mint", {"who": "x", "board": BOARD}), ("key.revoke", {"key": "k"})):
        with pytest.raises(Refused, match="member may not"):
            admin(server, hers, verb, args)


def test_the_owner_lists_every_board_and_a_member_only_their_own(
    server: BoardServer, owner: str, tmp_path: Path
) -> None:
    """"Their own" is DERIVED from the credentials they hold, not a membership
    table that would have to be kept in step with them."""
    hers, _ = member(server, tmp_path)
    admin(server, owner, "board.create", {"name": "otro"})

    seen = admin(server, owner, "board.list", {})
    assert seen["role"] == "owner"
    assert [row["name"] for row in seen["boards"]] == [BOARD, "otro"]
    assert seen["boards"][0]["cards"] == 0 and seen["boards"][0]["seq"] >= 0

    theirs = admin(server, hers, "board.list", {})
    assert theirs["role"] == "member"
    assert [row["name"] for row in theirs["boards"]] == [BOARD]  # not `otro`


def test_a_revoked_credential_stops_showing_its_board_to_the_member(
    server: BoardServer, owner: str, tmp_path: Path
) -> None:
    """The other half of deriving membership from credentials: it has to derive
    the ABSENCE too. `boards()` counts live rows only — otherwise revoking
    somebody's access would leave the board on their list forever, which is the
    stored-status bug this project refuses everywhere else."""
    hers, _ = member(server, tmp_path)
    assert server.mounts.credentials.boards(ANA) == {BOARD}  # and never the `*` session
    assert [row["name"] for row in admin(server, hers, "board.list", {})["boards"]] == [BOARD]

    for row in server.mounts.credentials._query(  # noqa: SLF001
        "SELECT id FROM credentials WHERE subject = ? AND board = ?", (ANA, BOARD)
    ):
        admin(server, owner, "invite.revoke", {"invite": str(row[0])})
    assert server.mounts.credentials.boards(ANA) == set()
    assert admin(server, hers, "board.list", {})["boards"] == []


def test_an_invite_minted_over_the_api_joins_end_to_end(
    server: BoardServer, owner: str, tmp_path: Path
) -> None:
    """Criterion 3: the line printed on the laptop works on another machine. The
    mint is the board's OWN Credentials — the same machinery the on-box command
    runs, reached through the API instead of a shell."""
    made = admin(server, owner, "invite.mint", {"who": "ana", "board": BOARD})
    assert made["board"] == BOARD and made["id"]

    hers = keygen(tmp_path / "ana_key")
    got = _redeem(url_of(server), str(made["token"]), "ana", f"{hers}.pub")
    assert RemoteBoard(url_of(server), got["token"], ANA).call("board", {})["seq"] >= 0
    assert sign_in(server, "ana", hers)["role"] == "member"


def test_an_invite_for_a_board_this_host_does_not_serve_is_refused_at_the_MINT(
    server: BoardServer, owner: str
) -> None:
    """Not at the join, a day later and a machine away from the typo."""
    with pytest.raises(NotFound, match="no board named"):
        admin(server, owner, "invite.mint", {"who": "ana", "board": "inventado"})
    assert not (server.mounts.root / "inventado").exists()


def test_revoking_an_invite_takes_it_back_and_a_typo_is_refused_not_swallowed(
    server: BoardServer, owner: str
) -> None:
    """`revoke` is an UPDATE, and an UPDATE that matches nothing succeeds — so a
    mistyped id used to print "revoked" while the real credential stayed live."""
    made = admin(server, owner, "invite.mint", {"who": "ana", "board": BOARD})
    assert admin(server, owner, "invite.revoke", {"invite": made["id"]})["revoked"] is True
    with pytest.raises(Refused, match="was revoked"):
        _redeem(url_of(server), str(made["token"]), "ana")

    with pytest.raises(Refused, match="minted no credential"):
        admin(server, owner, "invite.revoke", {"invite": "notanid"})


def test_revoking_a_key_stops_it_signing_anybody_in(
    server: BoardServer, owner: str, tmp_path: Path
) -> None:
    """The store rewrites `allowed_signers` whole, so one revoked row is enough:
    the next `ssh-keygen -Y verify` runs against a file that no longer names it."""
    hers, key = member(server, tmp_path)
    fingerprint = [k.fingerprint for k in server.mounts.host.store().keys("ana")][0]

    gone = admin(server, owner, "key.revoke", {"key": fingerprint})
    assert gone["principal"] == "ana" and gone["revoked"] is True
    with pytest.raises(TaskopsError):
        sign_in(server, "ana", key)

    with pytest.raises(Refused, match="no key"):
        admin(server, owner, "key.revoke", {"key": "SHA256:nothing"})


# ── the host enrols a whole team in one call: members.enroll ────────────────
#
# The seam the forge sync stands on. Everything here is principals and ssh key
# lines: this door does not know what GitHub is, and the tests do not mention it
# either — real keypairs, a real socket, and the same `allowed_signers` the
# login tests verify signatures against.


def enrol(server: BoardServer, token: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return admin(server, token, "members.enroll", {"members": rows})


def pubkey(key: Path) -> str:
    return Path(f"{key}.pub").read_text(encoding="utf-8")


def team(tmp_path: Path, *names: str) -> dict[str, Path]:
    return {name: keygen(tmp_path / f"{name}_key") for name in names}


def signers_of(server: BoardServer) -> str:
    return (server.mounts.root / "allowed_signers").read_text(encoding="utf-8")


def test_one_batch_enrols_a_team_and_re_running_it_leaves_the_same_state(
    server: BoardServer, owner: str, tmp_path: Path
) -> None:
    """Criteria 1 and 4. The batch is the seam the owner's sync will call, so the
    second run is the whole test: same input, same state, and `allowed_signers`
    byte for byte — a key already live is SKIPPED rather than written again."""
    keys = team(tmp_path, "ana", "leo")
    batch = [{"principal": name, "keys": [pubkey(key)]} for name, key in keys.items()]

    first = enrol(server, owner, batch)
    assert first["enrolled"] == ["ana", "leo"]
    assert [row["principal"] for row in first["added"]] == ["ana", "leo"]
    assert first["unchanged"] == [] and first["skipped"] == []
    assert first["signers"] == 3  # berna's own key, and the two just enrolled

    # A new principal is a MEMBER, and its key really signs — the file the login
    # verifies against was regenerated whole, not appended to.
    store = server.mounts.host.store()
    assert [(p.name, p.role) for p in store.principals()] == [
        ("ana", "member"), ("berna", "owner"), ("leo", "member")
    ]
    assert sign_in(server, "ana", keys["ana"])["role"] == "member"
    written = signers_of(server)
    assert sorted(line.split()[0] for line in written.splitlines()) == ["ana", "berna", "leo"]
    held = store.keys(live=False)

    again = enrol(server, owner, batch)
    assert again["enrolled"] == [] and again["added"] == []
    assert again["unchanged"] == ["ana", "leo"] and again["skipped"] == []
    assert signers_of(server) == written
    assert store.keys(live=False) == held


def test_the_owner_re_enrolled_stays_owner_and_the_keys_accumulate(
    server: BoardServer, owner: str, keyed: Path, tmp_path: Path
) -> None:
    """Criterion 2, and the property `test_a_re_join_never_demotes_the_owner…`
    pins for the invite door: the batch goes through `login.register`, so an
    existing principal only ever gains a KEY. Reaching past it to
    `ServerStore.enroll` — an INSERT OR REPLACE on principals — would hand the
    owner back as a member the first time a sync named them."""
    laptop = keygen(tmp_path / "berna_laptop")
    out = enrol(server, owner, [{"principal": "berna", "keys": [pubkey(keyed), pubkey(laptop)]}])

    assert out["enrolled"] == []  # berna existed; nothing was created
    assert [row["principal"] for row in out["added"]] == ["berna"]  # the laptop key only
    store = server.mounts.host.store()
    assert store.role_of("berna") == "owner"
    assert len(store.keys("berna")) == 2
    assert sign_in(server, "berna", laptop)["role"] == "owner"  # both keys sign


def test_enrolling_members_is_the_server_owners_move_and_a_member_is_refused_BY_ROLE(
    server: BoardServer, owner: str, tmp_path: Path
) -> None:
    """Criterion 3. Whoever may run this decides who exists on the host, so it is
    `key.add`'s wall and not a softer one — and the refusal names the role that
    may, from `core/scope.py::permit` and not a second copy of the rule."""
    hers, _ = member(server, tmp_path)
    mallory = keygen(tmp_path / "mallory_key")

    with pytest.raises(Refused) as refused:
        enrol(server, hers, [{"principal": "mallory", "keys": [pubkey(mallory)]}])
    assert "member may not members.enroll" in str(refused.value)
    assert "owner may" in str(refused.value)
    assert server.mounts.host.store().principal("mallory") is None


def test_a_revoked_key_is_not_resurrected_and_another_principals_key_is_not_moved(
    server: BoardServer, owner: str, tmp_path: Path
) -> None:
    """Two keys the batch refuses to write, and REPORTS instead of obeying: a
    revocation a re-run would undo, and a fingerprint that belongs to somebody
    else — the primary key is the fingerprint, so writing it would move the key
    off its holder and quietly stop them signing."""
    keys = team(tmp_path, "ana", "leo")
    enrol(server, owner, [{"principal": "ana", "keys": [pubkey(keys["ana"])]}])
    fingerprint = server.mounts.host.store().keys("ana")[0].fingerprint
    admin(server, owner, "key.revoke", {"key": fingerprint})

    out = enrol(
        server,
        owner,
        [
            {"principal": "ana", "keys": [pubkey(keys["ana"])]},
            {"principal": "leo", "keys": [pubkey(keys["ana"]), pubkey(keys["leo"])]},
        ],
    )
    leo = server.mounts.host.store().keys("leo")[0].fingerprint
    assert out["added"] == [{"principal": "leo", "fingerprint": leo}]
    assert [(row["principal"], row["fingerprint"]) for row in out["skipped"]] == [
        ("ana", fingerprint), ("leo", fingerprint)
    ]
    assert "does not undo a revocation" in out["skipped"][0]["why"]
    assert "ana already holds this key" in out["skipped"][1]["why"]

    # The revocation still stands, and the key is still ana's.
    with pytest.raises(TaskopsError):
        sign_in(server, "ana", keys["ana"])
    held = server.mounts.host.store().keys(live=False)
    assert [(k.principal, k.revoked) for k in held if k.fingerprint == fingerprint] == [
        ("ana", True)
    ]


def test_a_batch_is_validated_WHOLE_and_a_bad_entry_enrols_nobody(
    server: BoardServer, owner: str, tmp_path: Path
) -> None:
    """A malformed key in the second entry would otherwise leave the first
    enrolled and the command re-run against a half-applied host — so the names
    and the key grammar are checked before a single row is written."""
    keys = team(tmp_path, "ana", "leo")
    good = {"principal": "ana", "keys": [pubkey(keys["ana"])]}

    with pytest.raises(BadRequest, match="not an ssh public key"):
        enrol(server, owner, [good, {"principal": "leo", "keys": ["not-a-key"]}])
    with pytest.raises(BadRequest, match="1-40 chars"):
        enrol(server, owner, [good, {"principal": "Leo Messi", "keys": [pubkey(keys["leo"])]}])
    with pytest.raises(BadRequest, match="taskops invite leo"):
        enrol(server, owner, [good, {"principal": "leo", "keys": []}])
    with pytest.raises(BadRequest, match="this call needs members="):
        enrol(server, owner, [])

    store = server.mounts.host.store()
    assert [p.name for p in store.principals()] == ["berna"]
    assert signers_of(server).splitlines() == [f"berna {store.keys('berna')[0].keyline}"]


def test_the_answer_names_who_the_batch_did_NOT_name_and_revokes_nobody(
    server: BoardServer, owner: str, tmp_path: Path
) -> None:
    """The drift, reported and never acted on: a principal enrolled by invite has
    no reason to be in a forge's collaborator list, and a sync that never heard of
    them would revoke them for existing. So `others` carries them — with the
    fingerprints the owner's own `taskops revoke --key` takes — and the batch
    itself touches nobody outside its own list."""
    hers, ana_key = member(server, tmp_path)
    keys = team(tmp_path, "leo")

    out = enrol(server, owner, [{"principal": "leo", "keys": [pubkey(keys["leo"])]}])
    store = server.mounts.host.store()
    assert out["others"] == [
        {"principal": "ana", "role": "member", "keys": [store.keys("ana")[0].fingerprint]},
        {"principal": "berna", "role": "owner", "keys": [store.keys("berna")[0].fingerprint]},
    ]
    # Reported, and that is ALL: ana still signs in and her board is still hers.
    assert sign_in(server, "ana", ana_key)["role"] == "member"
    assert [row["name"] for row in admin(server, hers, "board.list", {})["boards"]] == [BOARD]


def test_a_board_credential_cannot_operate_the_host_and_the_refusal_names_the_key(
    server: BoardServer, keyed: Path
) -> None:
    """The session is board `*` scoped, so a board token cannot reach this door —
    and the sentence it gets back is how a key gets registered, not a code."""
    board_token, _ = server.mounts.credentials.mint(BERNA, BOARD, _clock.now())
    for token in (board_token, ""):
        with pytest.raises(Refused) as refused:
            admin(server, token, "board.list", {})
        assert "--key ~/.ssh/id_ed25519" in str(refused.value)


def test_an_unknown_server_verb_names_the_ones_this_host_has(
    server: BoardServer, owner: str
) -> None:
    """Every verb this host has, not a hand-copied prefix of them: the registry is
    what the refusal must stay in step with, and a list written out here goes
    stale the first time a verb is added (it did, at `board.ingest`)."""
    from taskops.http.admin import REGISTRY

    with pytest.raises(BadRequest) as refused:
        admin(server, owner, "board.destroy", {})
    assert str(refused.value).endswith(", ".join(sorted(REGISTRY)))


def test_the_root_rpc_is_the_server_and_a_board_named_rpc_is_still_reachable(
    server: BoardServer, owner: str
) -> None:
    """Why the door is `/rpc` and not `/admin/rpc`: `admin` is a legal board name,
    so a two-segment door would collide with a real board's own. One segment
    cannot — and this proves the pair stays apart even for the worst name."""
    admin(server, owner, "board.create", {"name": "admin"})
    token, _ = server.mounts.credentials.mint(BERNA, "admin", _clock.now())
    base = f"http://127.0.0.1:{server.server_address[1]}/admin"
    status, body = _get_post(base, token, {"verb": "board", "actor": BERNA})
    assert status == 200 and body["data"]["groups"]["take"] == []


@pytest.fixture()
def joined(
    server: BoardServer, keyed: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """A checkout joined to this host WITH the owner's key, and cwd inside it —
    which is the whole setup the four commands assume: the host comes from the
    join, so nothing repeats an address and no alias registry has to exist."""
    from taskops.cli import commands

    invite, _ = server.mounts.credentials.mint("invite:berna", BOARD, _clock.now(), once=True)
    project = tmp_path / "mine"
    (project / ".git").mkdir(parents=True)
    monkeypatch.setenv("TASKOPS_ACTOR", BERNA)
    commands.join(project, f"{url_of(server)}?invite={invite}", BERNA, str(keyed))
    monkeypatch.chdir(project)
    return project


def test_the_four_commands_run_from_a_joined_checkout_with_no_address_repeated(
    server: BoardServer, joined: Path, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Criterion 3 end to end, through `main()` and the real argv: create a board
    from the laptop, list it, invite somebody, and JOIN with the line that was
    printed — on another machine, against the server that minted it."""
    from taskops.cli import main
    from taskops.cli.commands import join

    assert main(["board", "create", "nuevo"]) == 0
    assert main(["board", "ls"]) == 0
    assert main(["invite", "ana", "--board", "nuevo"]) == 0
    printed = capsys.readouterr().out
    assert "nuevo created on" in printed and "nuevo" in printed

    line = [row.strip() for row in printed.splitlines() if row.strip().startswith("taskops join")]
    assert "--key" in line[0]  # the line it prints is the KEYED join, not the legacy one
    assert len(line) == 1, printed
    url = line[0].split('"')[1]  # the join line, verbatim, as a human would paste it
    hers = keygen(tmp_path / "ana_id")
    theirs = tmp_path / "hers"
    (theirs / ".git").mkdir(parents=True)
    join(theirs, url, "dev:ana", str(hers))
    token = json.loads((theirs / ".taskops" / "remote.json").read_text())["token"]
    fresh = f"http://127.0.0.1:{server.server_address[1]}/nuevo"
    assert RemoteBoard(fresh, token, ANA).call("board", {})["seq"] >= 0


def test_an_admin_command_re_mints_its_own_session_and_asks_nobody(
    server: BoardServer, joined: Path, clock: Any
) -> None:
    """These commands take `session.fresh`, not the token lying in the file — so
    a laptop that ran one yesterday runs one today with nobody asked for
    anything. Without it the four verbs would be the only thing in taskops that
    still needs a human to notice a credential ran out."""
    from taskops.cli import main

    spent = json.loads((joined / ".taskops" / "remote.json").read_text())["token"]
    clock(12 * 3600.0 + 60.0)  # a day later, that session is dead
    assert main(["board", "ls"]) == 0
    minted = json.loads((joined / ".taskops" / "remote.json").read_text())["token"]
    assert minted != spent
    with pytest.raises(Refused, match="expired"):
        admin(server, spent, "board.list", {})


def test_the_address_may_be_a_whole_url_and_a_url_is_never_split_by_slashes(
    server: BoardServer, joined: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`<host>/<name>` as ONE argument is the documented form, and it has to
    survive the case that breaks the naive parse: `https://h:1/b` has three
    slashes and `h/b` has one. The scheme decides, never the count — otherwise
    `taskops board ls https://host` creates a board called `host`."""
    from taskops.cli import main

    assert main(["board", "create", f"{host_of(server)}/desdeurl"]) == 0
    assert (server.mounts.root / "desdeurl").is_dir()

    assert main(["board", "ls", host_of(server)]) == 0  # a bare host names no board
    listed = capsys.readouterr().out
    assert "desdeurl" in listed and BOARD in listed
    assert not (server.mounts.root / host_of(server).rpartition("/")[2]).exists()


def test_revoke_takes_exactly_one_of_key_and_invite(server: BoardServer, joined: Path) -> None:
    """Neither is a command with no object; both is two acts wearing one word."""
    from taskops.cli import main
    from taskops.cli.grants import revoke

    for argv in (["revoke"], ["revoke", "--key", "SHA256:x", "--invite", "id"]):
        assert main(argv) == 1  # `main` prints the refusal and never raises
    with pytest.raises(TaskopsError, match="exactly one"):
        revoke(_argv("revoke", key="", invite="", host="", root=""))


def test_a_command_outside_any_joined_checkout_says_which_host_it_wants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No alias registry means the address has to come from somewhere, and the
    refusal names both places it can: --host, or the join that records one."""
    from taskops.cli.operate import board

    monkeypatch.chdir(tmp_path)
    with pytest.raises(TaskopsError, match="--host https://<host>"):
        board(_argv("board", action="ls", target=""))


def _argv(command: str, **fields: str) -> Any:
    from argparse import Namespace

    return Namespace(command=command, **fields)


# ── the FIRST command: --key, on a checkout that never joined ───────────────
#
# Everything above this line is run from `joined`, and that is exactly why the
# deadlock below survived 391 tests: the owner of a brand-new host has nothing
# to join. `taskops invite` mints the invite `join` wants, and it wanted a
# session of its own, for a board nobody had created yet. The only exit was ssh
# onto the box — the anomaly the chapter exists to kill. Found by running the
# chapter end to end on a clean host (2026-08-09), so these go through `main()`
# and the real argv: the WIRING was what was broken, and calling the functions
# is what hid it (the same lesson `upstream=` taught this chapter once already).


@pytest.fixture()
def virgin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A checkout that has never joined anything, and cwd inside it.

    HOME is a fixture directory with an EMPTY `.ssh`, and that is not tidiness:
    since key discovery exists, a bare verb reads `~/.ssh/id_ed25519`, so a test
    left on the real HOME would sign the runner's own key against a throwaway
    server and pass or fail by whose laptop it ran on."""
    project = tmp_path / "laptop"
    (project / ".git").mkdir(parents=True)
    (tmp_path / "home" / ".ssh").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("TASKOPS_ACTOR", BERNA)
    monkeypatch.chdir(project)
    return project


def test_the_owner_creates_the_first_board_from_the_laptop_with_only_a_key(
    server: BoardServer, keyed: Path, virgin: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Criteria 1 and 2. `server init` happened on the box (the `keyed` fixture);
    everything after it is this laptop, and the SECOND command carries no flags
    at all — not even the host, because the login it cached records one."""
    from taskops.cli import main

    assert main(["board", "create", f"{host_of(server)}/e2e", "--key", str(keyed)]) == 0
    assert (server.mounts.root / "e2e").is_dir()

    saved = json.loads((virgin / ".taskops" / "remote.json").read_text())
    # `board` joins the block with the name this very command chose: the address
    # is one fact, and the bare `board push` after it must not re-guess it.
    assert saved["login"] == {
        "host": host_of(server),
        "principal": "berna",
        "key": str(keyed),
        "board": "e2e",
    }
    assert saved["token"]

    capsys.readouterr()
    assert main(["board", "ls"]) == 0  # no --key, no --host: the session is cached
    assert "e2e" in capsys.readouterr().out
    assert main(["board", "visibility", "e2e", "public"]) == 0  # and so is every other verb


def test_invite_and_revoke_are_runnable_as_the_first_command_too(
    server: BoardServer, keyed: Path, virgin: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The other end of the deadlock: the invite that `join` needs is minted by a
    laptop that never joined. And `revoke` signs in with `--sign-key`, because on
    that verb `--key` is already the fingerprint being revoked."""
    from taskops.cli import main

    argv = ["invite", "ana", "--board", BOARD, "--host", host_of(server), "--key", str(keyed)]
    assert main(argv) == 0
    assert "taskops join" in capsys.readouterr().out

    _, made = server.mounts.credentials.mint("invite:ana", BOARD, _clock.now(), once=True)
    (virgin / ".taskops" / "remote.json").unlink()  # never joined, and no session cached either
    kill = ["revoke", "--invite", made.id, "--host", host_of(server), "--sign-key", str(keyed)]
    assert main(kill) == 0
    assert json.loads((virgin / ".taskops" / "remote.json").read_text())["login"]["principal"]


def test_as_names_the_principal_when_the_unix_user_is_not_it(
    server: BoardServer, keyed: Path, virgin: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Criterion 3. The $USER guess is wrong on any machine whose login name is
    not the principal's, and before `--as` such a machine could not sign in at
    all. The refused attempt also leaves NOTHING cached: a login block written
    before the host accepted the signature would be a config that lies."""
    from taskops.cli import main

    monkeypatch.delenv("TASKOPS_ACTOR", raising=False)
    monkeypatch.setenv("USER", "berna-laptop")
    assert main(["board", "create", f"{host_of(server)}/wrong", "--key", str(keyed)]) == 1
    assert not (server.mounts.root / "wrong").exists()
    assert "login" not in read_config(virgin)

    right = ["board", "create", f"{host_of(server)}/right", "--key", str(keyed), "--as", "berna"]
    assert main(right) == 0
    assert (server.mounts.root / "right").is_dir()
    assert read_config(virgin)["login"]["principal"] == "berna"


def test_with_no_session_and_no_key_the_refusal_names_both_doors(
    server: BoardServer, keyed: Path, virgin: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Criterion 4. It used to name only `join`, which is the one instruction the
    owner on day one cannot follow — so the sentence sent them to ssh."""
    from taskops.cli import main

    assert main(["board", "ls", host_of(server)]) == 1
    refusal = capsys.readouterr().err
    assert "--key ~/.ssh/id_ed25519" in refusal and "--as <principal>" in refusal
    assert "taskops join" in refusal
    # …and, since discovery, WHAT it tried: an empty `~/.ssh` is the other reason
    # this refusal appears, and a refusal that hides its search is unactionable.
    for name in ("id_ed25519", "id_ecdsa", "id_rsa"):
        assert f"~/.ssh/{name}" in refusal, name


# ── the git ergonomics: host once, key discovered, verbs bare ───────────────
#
# «esto debería ser como git — taskops remote add / board create / board push,
# pero sin --key». Git asks for neither a URL nor an identity file on every
# push, and both reasons are copied: the address is recorded per checkout, the
# key is discovered the way ssh discovers one. These go through `main()` and the
# real argv for the same reason the block above does — the WIRING is what three
# cards of this chapter got caught on.


@pytest.fixture()
def discoverable(server: BoardServer, tmp_path: Path, virgin: Path) -> Path:
    """The owner's key where SSH ITSELF would look, under the fixture HOME that
    `virgin` installed — the runner's real ~/.ssh is never read or written."""
    from taskops.cli import admin

    key = keygen(tmp_path / "home" / ".ssh" / "id_ed25519")
    admin.init(tmp_path / "boards", f"{key}.pub", "berna")
    return key


def test_remote_add_then_the_verbs_go_bare(
    server: BoardServer, discoverable: Path, virgin: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Criteria 1 and 3. Two commands, and the second carries a name only because
    this test wants a name it did not pick: no URL and no --key on either."""
    from taskops.cli import main

    assert main(["remote", "add", host_of(server)]) == 0
    assert main(["board", "create", "bare"]) == 0
    assert (server.mounts.root / "bare").is_dir()

    login = json.loads((virgin / ".taskops" / "remote.json").read_text())["login"]
    assert login == {
        "host": host_of(server),
        "principal": "berna",
        "key": str(discoverable),  # DISCOVERED, and recorded as if it had been --key
        "board": "bare",
    }
    capsys.readouterr()
    assert main(["board", "ls"]) == 0 and "bare" in capsys.readouterr().out
    assert main(["board", "visibility", "public"]) == 0  # bare: the recorded name


def test_join_goes_bare_too_and_the_key_is_the_whole_credential(
    server: BoardServer, discoverable: Path, virgin: Path
) -> None:
    """`remote add` once, then `taskops join <name>` — no URL, no token, no
    --key. The discovered key signs in, exactly as every board verb does, and
    what lands in remote.json is a SESSION plus the login block that renews it.
    Keys exist so tokens do not travel."""
    from taskops.cli import main
    from taskops.board import open_board

    dev = client(server, BERNA)
    plan(dev)  # the board has content, so the joined checkout can prove it reads
    assert main(["remote", "add", host_of(server)]) == 0
    assert main(["join", BOARD]) == 0

    config = json.loads((virgin / ".taskops" / "remote.json").read_text())
    assert config["login"]["key"] == str(discoverable)  # DISCOVERED, recorded
    assert config["token"]  # a session, minted by the key
    assert config["token_expires"] > 0  # with an expiry — never a standing token
    board = json.loads((virgin / ".taskops" / "board.json").read_text())
    assert board["url"] == f"{host_of(server)}/{BOARD}"
    assert open_board(virgin, BERNA).call("board", {})["groups"]["take"]


def test_a_bare_join_with_an_unregistered_key_leaves_nothing_behind(
    server: BoardServer, virgin: Path, tmp_path: Path
) -> None:
    """The sign-in is proved BEFORE anything is written: a refused key must not
    leave a half-joined checkout that every later command trips over."""
    from taskops.cli import main, admin

    admin.init(tmp_path / "boards", f'{keygen(tmp_path / "owner_key")}.pub', "berna")
    keygen(tmp_path / "home" / ".ssh" / "id_ed25519")  # discoverable, NOT enrolled
    assert main(["remote", "add", host_of(server)]) == 0
    assert main(["join", BOARD]) == 1
    assert not (virgin / ".taskops" / "board.json").exists()
    # remote.json holds exactly what `remote add` wrote — the refused join
    # added nothing: no token, no principal, no key.
    config = json.loads((virgin / ".taskops" / "remote.json").read_text())
    assert config == {"login": {"host": host_of(server)}}


def test_join_takes_the_invite_as_a_flag_not_a_query_string(
    server: BoardServer, virgin: Path, tmp_path: Path
) -> None:
    """The first join of a NEW teammate: `taskops join <name> --invite <id>`.
    The invite authorises the enrolment, the discovered key is what gets
    registered, and from then on the key is the credential — same end state as
    the URL form, without a token ever appearing on a command line."""
    from taskops.cli import main, admin

    admin.init(tmp_path / "boards", f'{keygen(tmp_path / "owner_key")}.pub', "berna")
    hers = keygen(tmp_path / "home" / ".ssh" / "id_ed25519")
    invite, _ = server.mounts.credentials.mint("invite:ana", BOARD, _clock.now(), once=True)
    assert main(["remote", "add", host_of(server)]) == 0
    assert main(["join", BOARD, "--invite", invite, "--as", "dev:ana"]) == 0

    config = json.loads((virgin / ".taskops" / "remote.json").read_text())
    assert config["login"] == {
        "host": host_of(server),
        "principal": "ana",
        "key": str(hers),
    }
    # Enrolled AND signed in by the one command: the session in the file was
    # minted by ana's key against /login, which only a registered key passes.
    assert config["token"] and config["token_expires"] > 0


def test_a_board_nobody_named_takes_the_directory_name(
    server: BoardServer, discoverable: Path, virgin: Path
) -> None:
    """Criterion 3, `gh repo create`'s convention: the checkout is `laptop/`."""
    from taskops.cli import main

    assert main(["remote", "add", host_of(server)]) == 0
    assert main(["board", "create"]) == 0
    assert (server.mounts.root / virgin.name).is_dir()


def test_the_name_board_create_chose_is_the_one_bare_push_uses(
    server: BoardServer, discoverable: Path, virgin: Path
) -> None:
    """The amendment's own scenario. A custom name followed by a bare `push` used
    to re-derive the DIRECTORY name, find no such board and refuse — making the
    human repeat a name they had already chosen. The recorded name beats it."""
    from taskops.cli import main
    from taskops.cli.remote import default_board

    assert main(["remote", "add", host_of(server)]) == 0
    assert main(["board", "create", "minombre"]) == 0
    assert default_board(virgin) == "minombre" != virgin.name

    seed_local_board(virgin)
    assert main(["board", "push"]) == 0
    assert json.loads((virgin / ".taskops" / "board.json").read_text())["url"].endswith("/minombre")


def test_discovery_tries_sshs_identity_files_in_sshs_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Criterion 2. `ssh_config(5)`'s order, and `--key` is the override (`ssh -i`).
    Files, not keys: what exists is what is tried, so this needs no crypto."""
    from taskops import identity

    home = tmp_path / "elsewhere"
    (home / ".ssh").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    assert identity.discover_key() is None

    (home / ".ssh" / "id_rsa").write_text("x")
    assert identity.discover_key() == home / ".ssh" / "id_rsa"
    (home / ".ssh" / "id_ecdsa").write_text("x")
    assert identity.discover_key() == home / ".ssh" / "id_ecdsa"
    (home / ".ssh" / "id_ed25519").write_text("x")
    assert identity.discover_key() == home / ".ssh" / "id_ed25519"


def test_remote_add_refuses_a_second_different_host_without_replace(
    server: BoardServer, virgin: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Criterion 5. Where a board lives is a decision, not a typo — and every bare
    verb afterwards points at whatever is recorded, so a silent overwrite is how
    a push lands on the wrong server. `taskops remote` prints what is recorded."""
    from taskops.cli import main

    assert main(["remote", "add", host_of(server) + "/"]) == 0  # a trailing slash is not a host
    capsys.readouterr()
    assert main(["remote"]) == 0 and host_of(server) in capsys.readouterr().out

    assert main(["remote", "add", "https://otro.example.com"]) == 1
    assert "--replace" in capsys.readouterr().err
    assert main(["remote", "add", host_of(server)]) == 0  # the SAME host is not a conflict
    assert main(["remote", "add", "https://otro.example.com", "--replace"]) == 0
    assert main(["remote", "add", "no-scheme.example.com", "--replace"]) == 1
    assert "not a host URL" in capsys.readouterr().err


def test_the_explicit_host_slash_name_form_is_unchanged_by_any_of_it(
    server: BoardServer, discoverable: Path, virgin: Path
) -> None:
    """Criterion 4. The URL form is git's other spelling and it wins over both the
    recorded host and the recorded name — that is what makes it explicit."""
    from taskops.cli import main

    assert main(["remote", "add", "https://otro.example.com"]) == 0
    assert main(["board", "create", f"{host_of(server)}/explicito", "--key", str(discoverable)]) == 0
    assert (server.mounts.root / "explicito").is_dir()
    # and the checkout still operates the host IT recorded: an explicit call is
    # one call, never a re-pointing of the clone (`identity.is_own_host`).
    login = json.loads((virgin / ".taskops" / "remote.json").read_text())["login"]
    assert login == {"host": "https://otro.example.com"}


def test_operating_another_host_leaves_this_checkouts_own_session_alone(
    server: BoardServer, keyed: Path, joined: Path
) -> None:
    """`remote.json` holds ONE session, for the board this repo reads. Signing in
    to a DIFFERENT server from inside a joined checkout is a legitimate thing to
    do, and it must not leave this repo renewing itself somewhere else."""
    from taskops.cli import main

    before = json.loads((joined / ".taskops" / "remote.json").read_text())
    other = f"http://localhost:{server.server_address[1]}"  # the same process, another address
    assert main(["board", "create", f"{other}/otro", "--key", str(keyed)]) == 0
    assert (server.mounts.root / "otro").is_dir()
    assert json.loads((joined / ".taskops" / "remote.json").read_text()) == before


def test_the_on_box_commands_survive_as_the_break_glass_path(tmp_path: Path) -> None:
    """The server being down is exactly when its API cannot be the only door.
    `--root` runs the same acts against the files, and it is NOT deprecated."""
    from taskops.cli import main
    from taskops.store.creds import Credentials

    root = tmp_path / "boards"
    (root / BOARD).mkdir(parents=True)
    assert main(["invite", "ana", "--board", BOARD, "--root", str(root)]) == 0
    creds = Credentials(root / "live.sqlite")
    try:
        ident = creds._query("SELECT id FROM credentials", ())[0][0]  # noqa: SLF001
        assert main(["revoke", "--invite", str(ident), "--root", str(root)]) == 0
        assert creds._query("SELECT revoked FROM credentials", ())[0][0] == 1  # noqa: SLF001
    finally:
        creds.close()


def test_readme_operations_use_ssh_only_to_install_and_bootstrap(tmp_path: Path) -> None:
    """Criterion 4, held by a test because prose rots silently. Every `ssh <host>`
    left in the README is an install or `server init`; the four admin acts are
    taskops commands, run from anywhere."""
    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")
    lines = [line.strip() for line in readme.splitlines() if "ssh <host>" in line]
    allowed = ("venv", "pip install", "rollback", "mkdir -p /tmp", "pm2", "taskops server init")
    assert lines, "the README still has to say how a host is installed"
    for line in lines:
        assert any(word in line for word in allowed), line
    for command in ("taskops board create", "taskops board ls", "taskops revoke --"):
        assert command in readme, command


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
    """`taskops serve` with a board that declares NO forge: its /ui/ is ONE
    sentence at 410. (The wording grew with §16's hosted window — tk-d0b464 —
    and now names BOTH ways out, `taskops ui` and `taskops board forge`; what
    this test PINS — a plain-text 410, one human sentence, no page — was the
    contract all along and is unchanged. The old "never coming back" clause
    pinned the pre-mirror implementation, not the contract: coming back was
    always the owner's move, and now there is one.)"""
    assert server.mounts.ui is None and server.mounts.repo is None
    with pytest.raises(HTTPError) as caught:
        urlopen(f"{url_of(server)}/ui/", timeout=5)
    answer = caught.value
    body = answer.read().decode()
    assert answer.code == 410
    assert answer.headers["Content-Type"].startswith("text/plain")
    assert "taskops ui" in body
    assert "taskops board forge <owner>/<repo>" in body
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
    door — since §16's hosted window, that door is the board's own move:
    `taskops board forge <owner>/<repo>`, whose mirror is what a serve-mode
    host may read. (The old wording named `taskops ui`; what this test PINS —
    a 404 that says which case it is — is unchanged, the words followed the
    amended NO_REPO meaning.) The switch is still a decided fact, per board."""
    assert server.mounts.repo is None
    status, body = _get(f"{url_of(server)}/git/commit/HEAD", _token(server, BERNA))
    assert status == 404 and body["ok"] is False
    assert body["error"]["code"] == "not_found"
    assert "not a repository" in body["error"]["message"]
    assert "taskops board forge <owner>/<repo>" in body["error"]["message"]


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


# ── the MIRROR: a serve-mode host answering /git from the declared forge ────
#
# §16, "The hosted window": a board host holds no checkout, but a board whose
# owner declared a forge may be answered from `<root>/<board>/mirror.git` — a
# bare, read-only clone of that forge. No network in these tests: the mirror
# is pre-cloned from a LOCAL fixture repo through the same `url=` override an
# owner's ssh deploy-key remote uses (`gitwork/mirror.py::ensure` returns an
# existing mirror untouched, which is exactly how that override survives).


def _declare_forge(httpd: BoardServer) -> None:
    client(httpd, BERNA).call("project", {"op": "forge", "repo": "bernatch22/taskops"})


def _mirrored(httpd: BoardServer, tmp_path: Path) -> Path:
    """Declare the forge and pre-clone the board's mirror from a local fixture
    forge — the owner's move for a private repo, and the test's for no network."""
    from taskops.gitwork import mirror as mirrors
    from tests.test_mirror import forge_repo

    forge = forge_repo(tmp_path)
    _declare_forge(httpd)
    made = mirrors.ensure(httpd.mounts.root / BOARD, None, url=str(forge))
    assert made is not None
    return forge


def test_a_serve_host_with_a_forge_board_answers_git_from_the_mirror(
    server: BoardServer, tmp_path: Path
) -> None:
    """Acceptance 1: same doors, same payload shape — the reader cannot tell a
    mirror from a checkout, and the resolved repo is cached per board."""
    _mirrored(server, tmp_path / "fixture")
    status, body = _get(f"{url_of(server)}/git/commit/HEAD", _token(server, BERNA))
    assert status == 200 and body["ok"] is True
    assert body["data"]["stat"] == {"README.md": [1, 0]}
    # resolved once and kept, the way stores are — never re-sniffed per request
    assert server.mounts.repos._mirrors[BOARD] == server.mounts.root / BOARD / "mirror.git"
    # the compare door reads from the same mirror, same vocabulary
    status, body = _get(
        f"{url_of(server)}/git/compare/main...main", _token(server, BERNA)
    )
    assert status == 200
    assert set(body["data"]) == {"base", "head", "stat", "patch", "truncated", "cap"}


def test_a_report_renders_from_the_mirror_through_the_file_door(
    server: BoardServer, tmp_path: Path
) -> None:
    """Acceptance 2 (milestone): report bytes come through the existing
    gitdoor file route, read from the mirror instead of a reader's clone."""
    from urllib.parse import quote

    from tests.test_mirror import run

    forge = _mirrored(server, tmp_path / "fixture")
    report = forge / ".taskops" / "reports" / "note.md"
    report.parent.mkdir(parents=True)
    report.write_text("# hello from the forge\n", encoding="utf-8")
    run.must("add", "-A", cwd=forge)
    run.must("commit", "-q", "-m", "a report", cwd=forge)
    sha = run.must("rev-parse", "HEAD", cwd=forge)
    path = quote(".taskops/reports/note.md", safe="")
    # the commit landed on the forge AFTER the clone, so serving it also walks
    # the file door through its one on-demand refresh — the mirror catches up
    status, body = _get(f"{url_of(server)}/git/file/{sha}?path={path}", _token(server, BERNA))
    assert status == 200
    assert body["data"]["text"].rstrip("\n") == "# hello from the forge"
    assert body["data"]["content_type"] == "text/markdown"


def test_a_missing_ref_on_a_mirror_buys_exactly_one_fetch_then_answers(
    server: BoardServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Acceptance 3 (milestone): one bounded on-demand fetch before stale —
    and a ref already present costs no network at all."""
    from taskops.gitwork import mirror as mirrors
    from tests.test_mirror import commit

    forge = _mirrored(server, tmp_path / "fixture")
    sha = commit(forge, "later.txt")  # exists on the forge, not in the mirror yet
    fetches: list[Path] = []
    real = mirrors.fetch

    def counted(mirror_path: Path) -> bool:
        fetches.append(mirror_path)
        return real(mirror_path)

    monkeypatch.setattr(mirrors, "fetch", counted)
    status, body = _get(f"{url_of(server)}/git/commit/{sha}", _token(server, BERNA))
    assert status == 200 and len(fetches) == 1
    assert body["data"]["stat"] == {"later.txt": [1, 0]}
    # now present: the same ask touches the network zero more times
    status, _ = _get(f"{url_of(server)}/git/commit/{sha}", _token(server, BERNA))
    assert status == 200 and len(fetches) == 1


def test_a_windows_own_clone_never_fetches_on_a_missing_ref(
    repo_server: BoardServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§16's local sentence still holds: "Nothing is fetched for you" — a
    background fetch would move a branch under an inhabited worktree."""
    from taskops.gitwork import mirror as mirrors

    fetches: list[Path] = []
    monkeypatch.setattr(mirrors, "fetch", lambda path: fetches.append(path) or False)
    status, body = _get(
        f"{url_of(repo_server)}/git/commit/deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        _token(repo_server, BERNA),
    )
    assert status == 404 and "not in your clone yet" in body["error"]["message"]
    assert fetches == []


def test_the_windows_missing_ref_sentence_is_pinned_byte_for_byte(
    repo_server: BoardServer,
) -> None:
    """The WINDOW's words, whole — right for a reader who has a clone and may
    fetch into it. tk-9cde88 split the vocabulary by audience and this pin is
    the local half of the contract: the host got its own sentence, and these
    bytes did not move an inch in the split."""
    status, body = _get(
        f"{url_of(repo_server)}/git/commit/tk-dfaff7", _token(repo_server, BERNA)
    )
    assert status == 404
    assert body["error"]["message"] == (
        "tk-dfaff7 is not in your clone yet — `git fetch origin tk-dfaff7` "
        "brings it. The board is shared and the code is not: a card's branch "
        "reaches origin when it closes, and this window reads only the "
        "checkout it stands in. Nothing is fetched for you."
    )


def test_a_mirrored_hosts_missing_ref_sentence_speaks_to_a_reader_with_no_clone(
    server: BoardServer, tmp_path: Path
) -> None:
    """tk-9cde88: 0.5.1 served the window's sentence from the hosted board to
    a reader with NO clone — "your clone", "git fetch", "nothing is fetched
    for you", every clause false on a host that had in fact fetched. The
    host's refusal names the forge it mirrors, says a pruned card branch is
    normal, and tells the reader to run nothing."""
    _mirrored(server, tmp_path / "fixture")
    status, body = _get(
        f"{url_of(server)}/git/commit/tk-dfaff7", _token(server, BERNA)
    )
    assert status == 404
    message = body["error"]["message"]
    assert "your clone" not in message and "git fetch" not in message
    assert "github.com/bernatch22/taskops" in message  # the declared forge, named
    assert "pruned" in message and "normal, not a fault" in message


# ── the HOSTED window: /ui on a serve-mode host, per forge and visibility ───


def test_the_forge_fact_alone_opens_the_hosted_window(server: BoardServer) -> None:
    """Card acceptance 1: /<board>/ui/ serves the packaged bundle on a
    serve-mode host once the owner declares a forge — the FACT opens the page,
    no mirror is cloned for it (the page's own /git calls resolve one lazily
    when a diff is actually read)."""
    _declare_forge(server)
    token = _token(server, BERNA)
    with urlopen(f"{url_of(server)}/ui/?token={token}", timeout=5) as response:
        assert response.headers["Content-Type"].startswith("text/html")
        assert "<script" in response.read().decode().lower()
    with urlopen(f"{url_of(server)}/ui/app.js?token={token}", timeout=5) as response:
        assert response.headers["Content-Type"].startswith("text/javascript")
        assert response.read()
    assert server.mounts.repos._mirrors == {}  # the page cost no clone


def test_a_private_hosted_window_refuses_anonymous_exactly_as_rpc_does(
    server: BoardServer,
) -> None:
    """Same wall, same words: no second credential system on the page door. An
    anonymous GET on a private forge-backed board gets /rpc's join refusal —
    the JSON envelope, not the 410 sentence and not the bundle."""
    _declare_forge(server)
    with pytest.raises(HTTPError) as caught:
        urlopen(f"{url_of(server)}/ui/", timeout=5)
    with caught.value as err:
        assert err.code == 409
        body = json.loads(err.read().decode())
    assert body["error"]["code"] == "refused"
    assert "taskops join <url with ?token=" in body["error"]["message"]
    # a token lets the same request through — the wall is the credential
    with urlopen(f"{url_of(server)}/ui/?token={_token(server, BERNA)}", timeout=5) as ok:
        assert ok.status == 200


def test_a_public_hosted_window_serves_anonymous_and_writes_not_one_byte(
    server: BoardServer, owner: str
) -> None:
    """Card acceptance 2, §11's harshest rule on the newest door: a public
    board serves the page to a stranger, and the read leaves NO write of any
    kind — presence included, asserted against the store itself AND hash for
    hash, twice, because a second load is a second chance to write."""
    _declare_forge(server)
    publish(server, owner)
    before = _fingerprint(server)
    seen = dict(_presence(server))
    for _ in range(2):
        with urlopen(f"{url_of(server)}/ui/", timeout=5) as response:
            assert response.status == 200
            assert response.headers["Content-Type"].startswith("text/html")
            assert "<script" in response.read().decode().lower()
    assert _fingerprint(server) == before
    assert dict(_presence(server)) == seen
    assert "anon" not in dict(_presence(server))


# ── the board's OWN address is the page; the machine doors under /api ──────


def test_the_boards_own_address_is_the_page(server: BoardServer) -> None:
    """tk-32d2ba (a): GET /<board> and /<board>/ serve the dashboard on a
    serve-mode host for a forge-backed board, behind exactly the credential
    /rpc asks for — and the page's RELATIVE links resolve from that address:
    `./style.css` and `./app.js` arrive as /<board>/style.css, /<board>/app.js.
    The page still costs no clone: the forge FACT opens it, never the mirror."""
    _declare_forge(server)
    token = _token(server, BERNA)
    for suffix in ("", "/"):
        with urlopen(f"{url_of(server)}{suffix}?token={token}", timeout=5) as response:
            assert response.headers["Content-Type"].startswith("text/html")
            assert "<script" in response.read().decode().lower()
    with urlopen(f"{url_of(server)}/app.js?token={token}", timeout=5) as response:
        assert response.headers["Content-Type"].startswith("text/javascript")
        assert response.read()
    with urlopen(f"{url_of(server)}/style.css?token={token}", timeout=5) as response:
        assert response.headers["Content-Type"].startswith("text/css")
        assert response.read()
    assert server.mounts.repos._mirrors == {}  # the page cost no clone


def test_the_board_root_keeps_rpcs_credential_wall(server: BoardServer) -> None:
    """Same wall as /ui/'s, at the new address: a PRIVATE forge-backed board
    refuses an anonymous GET of its root with /rpc's join refusal, and the
    same request with a token gets the page. No second credential system."""
    _declare_forge(server)
    with pytest.raises(HTTPError) as caught:
        urlopen(f"{url_of(server)}/", timeout=5)
    with caught.value as err:
        assert err.code == 409
        body = json.loads(err.read().decode())
    assert body["error"]["code"] == "refused"
    assert "taskops join <url with ?token=" in body["error"]["message"]
    with urlopen(f"{url_of(server)}/?token={_token(server, BERNA)}", timeout=5) as ok:
        assert ok.status == 200


def test_a_board_root_with_no_forge_answers_the_same_410_sentence(
    server: BoardServer,
) -> None:
    """A board that declared no forge serves no page at its root either — the
    ONE plain-text sentence /ui/ answers, naming both ways out, so the two
    addresses of the same page cannot disagree about why it is not here."""
    with pytest.raises(HTTPError) as caught:
        urlopen(f"{url_of(server)}/", timeout=5)
    with caught.value as answer:
        body = answer.read().decode()
    assert answer.code == 410
    assert answer.headers["Content-Type"].startswith("text/plain")
    assert "taskops board forge <owner>/<repo>" in body


def test_a_tail_outside_the_bundles_closed_set_is_still_a_404(
    server: BoardServer,
) -> None:
    """The page's assets are a CLOSED set (`static.asset`): a tail that names
    no packaged file never reaches the page door, so a mistyped API path is
    still the honest 404 and the SPA fallback cannot swallow it — even on a
    forge-backed PUBLIC board, where the page itself is anonymous."""
    _declare_forge(server)
    for tail in ("nope.css", "app", "deep/app.js", "verbs"):
        with pytest.raises(HTTPError) as caught:
            urlopen(f"{url_of(server)}/{tail}?token={_token(server, BERNA)}", timeout=5)
        with caught.value as err:
            assert err.code == 404 and err.read()


def test_the_machine_doors_answer_under_api_too(server: BoardServer) -> None:
    """tk-32d2ba (b): /<board>/api/{rpc,git,feed} are the addresses the page
    uses from now on, and each answers EXACTLY as its bare 0.5.0 spelling —
    one strip in `routes.py::split`, so the two spellings share one handler,
    one credential, one set of words. Both are asserted side by side here so
    they cannot drift apart in silence."""
    token = _token(server, BERNA)
    old = _post(url_of(server), token, {"verb": "board", "actor": BERNA})
    new = _post(f"{url_of(server)}/api", token, {"verb": "board", "actor": BERNA})
    assert new["ok"] is True and new["data"] == old["data"]
    # /git: no repo on this host either way — the SAME refusal, naming the door
    old_status, old_body = _get(f"{url_of(server)}/git/commit/HEAD", token)
    new_status, new_body = _get(f"{url_of(server)}/api/git/commit/HEAD", token)
    assert (new_status, new_body) == (old_status, old_body)
    assert new_status == 404 and "taskops board forge" in new_body["error"]["message"]
    # /feed: the SSE door greets through the prefix exactly as it always has
    with urlopen(f"{url_of(server)}/api/feed?token={token}", timeout=5) as stream:
        assert b"hello" in stream.readline() + stream.readline()


def test_window_mode_is_unchanged_by_the_board_root(repo_server: BoardServer) -> None:
    """tk-32d2ba (d): `taskops ui` serves its page at the ROOT — that is the
    address it hands out — and mounts its board under /board, whose root is
    NOT a page (the page branch is serve-mode only: `mounts.ui is None`). The
    /api spelling still answers there, because the rebuilt bundle will speak
    it through a window too."""
    with urlopen(f"{url_of(repo_server, '')}", timeout=5) as response:
        assert response.headers["Content-Type"].startswith("text/html")
        assert "<script" in response.read().decode().lower()
    with pytest.raises(HTTPError) as caught:
        urlopen(f"{url_of(repo_server)}/", timeout=5)  # /board/: no page, as in 0.5.0
    with caught.value as err:
        assert err.code == 404 and err.read()
    token = _token(repo_server, BERNA)
    answer = _post(f"{url_of(repo_server)}/api", token, {"verb": "board", "actor": BERNA})
    assert answer["ok"] is True
    status, body = _get(f"{url_of(repo_server)}/api/git/commit/HEAD", token)
    assert status == 200 and body["data"]["stat"]  # the checkout answered, through /api


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


def test_a_window_whose_session_ran_out_signs_in_again_instead_of_dying(
    server: BoardServer,
) -> None:
    """A host session is twelve hours (`http/login.py::SESSION_TTL`) and a window
    is meant to be left open. It used to hold the token it was built with for the
    life of the process, so the morning after, every read answered "that
    credential expired" and the habit that taught was `taskops join` — pasting a
    credential the machine can mint itself (2026-08-18, berna's axion board).

    The retry is `board.py::RemoteBoard.call`'s and it is narrow: the SERVER said
    EXPIRED, and this process was handed a way to sign in."""
    from taskops.http.upstream import Upstream

    now = _clock.now()
    ran_out, _ = server.mounts.credentials.mint(BERNA, BOARD, now - 100.0, ttl=1.0)
    minted: list[str] = []

    def sign_in() -> str:
        token, _ = server.mounts.credentials.mint(BERNA, BOARD, _clock.now())
        minted.append(token)
        return token

    call = json.dumps({"verb": "board", "args": {}, "actor": BERNA}).encode()

    # WITH a way back in: one refusal nobody sees, one login, the board's answer.
    up = Upstream(url_of(server), ran_out, refresh=sign_in)
    status, answer = up.rpc(call)
    assert status == 200 and json.loads(answer)["ok"] is True
    assert len(minted) == 1 and up.token == minted[0] != ran_out

    # …and the session it just minted is kept: the SECOND call signs in nowhere.
    status, answer = up.rpc(call)
    assert status == 200 and len(minted) == 1

    # WITHOUT one — a standing bearer token, or a public viewer — the refusal is
    # the board's own and reaches the page exactly as it always did.
    mute = Upstream(url_of(server), ran_out)
    status, answer = mute.rpc(call)
    body = json.loads(answer)
    assert body["ok"] is False and "expired" in body["error"]["message"]
    assert mute.token == ran_out

    # And it is EXPIRY, never any other refusal: a credential this board never
    # issued is not a session to renew, and burning a login on one would turn
    # every typo into a round trip to the host.
    stranger = Upstream(url_of(server), "not-a-credential", refresh=sign_in)
    status, answer = stranger.rpc(call)
    assert json.loads(answer)["ok"] is False and len(minted) == 1


def test_a_window_opened_on_a_spent_session_mints_one_before_it_serves(
    server: BoardServer, keyed: Path, tmp_path: Path
) -> None:
    """The other half of the same day: not the window that was already open, but
    the one being opened NOW on a session that ran out overnight. `_upstream`
    read the token lying in the file, so `taskops ui` came up forwarding a dead
    credential — and every command BESIDE it (`board ls`, the four admin verbs)
    had taken `session.fresh` since the session chapter landed."""
    from taskops.cli import serving
    from taskops.gitwork import install

    project = tmp_path / "clone"
    door = {"host": host_of(server), "principal": "berna", "key": str(keyed)}
    install.write_config(project, url_of(server), "spent", door, _clock.now() - 1.0)

    upstream = serving._upstream(project)  # noqa: SLF001 — the decision under test
    assert upstream is not None and upstream.token not in ("", "spent")
    status, answer = upstream.rpc(json.dumps({"verb": "board", "args": {}}).encode())
    assert status == 200 and json.loads(answer)["ok"] is True


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
    # A STANDING bearer is never replaced behind its owner's back, so this
    # window has no way to sign in again and does not pretend to have one
    # (`session.py::refresher`, and the window's own retry hangs off exactly
    # this being None — `http/upstream.py`).
    assert upstream.refresh is None

    # With a `login` block it does: the session that expires overnight is minted
    # again from the key, in the process, instead of by a human typing join.
    (root / ".taskops" / "remote.json").write_text(
        json.dumps(
            {
                "token": "t0ken",
                "login": {"host": "https://boards.example", "principal": "berna", "key": "k"},
            }
        ),
        encoding="utf-8",
    )
    signed_in = serving._upstream(root)  # noqa: SLF001
    assert signed_in is not None and signed_in.refresh is not None


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


# ── public boards: anyone may watch, nobody writes without a key ────────────
#
# GitHub's model, deliberately: PRIVATE by default, the owner may publish,
# public means ANONYMOUS READ, and a write always needs a registered key. The
# harshest of these is `test_an_anonymous_crawl_moves_not_one_byte` — not "no
# new events" but byte-identical files, because the bug this chapter's second
# rule exists to prevent is a PRESENCE row, which no card and no event would
# ever show.

READS = ("board", "card", "report", "events", "mentions")
WRITES = ("plan", "take", "update", "bind", "project", "assign", "merged", "review")


def publish(httpd: BoardServer, owner: str, wanted: str = "public") -> dict[str, Any]:
    return admin(httpd, owner, "board.visibility", {"board": BOARD, "visibility": wanted})


def anon(httpd: BoardServer, verb: str, args: dict[str, Any] | None = None) -> tuple[int, Any]:
    """A call with NO Authorization header at all — a stranger with a browser."""
    request = Request(
        f"{url_of(httpd)}/rpc",
        data=json.dumps({"verb": verb, "args": args or {}}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            return int(response.status), json.loads(response.read().decode())
    except HTTPError as err:
        with err:  # an HTTPError IS a response: unclosed, it leaks the socket
            return int(err.code), json.loads(err.read().decode())


def _prints(body: Any) -> str:
    return str(body["error"]["message"])


def _fingerprint(httpd: BoardServer) -> dict[str, str]:
    """Every stored byte of the board EXCEPT the cache, which is derived and
    disposable by design (delete it and it rebuilds). live.sqlite is in WAL
    mode, so its -wal and -shm companions are hashed too: a presence INSERT
    lands in the write-ahead log first, and hashing the main file alone would
    call that write invisible — which is the whole failure being pinned."""
    board = httpd.mounts.root / BOARD
    return {
        path.name: sha256(path.read_bytes()).hexdigest()
        for path in sorted(board.iterdir())
        if path.is_file() and not path.name.startswith("cache.sqlite")
    }


def test_the_owner_publishes_a_board_and_a_member_may_not(
    server: BoardServer, owner: str, tmp_path: Path
) -> None:
    """Criterion: the flag is an owner-only server-scope verb, and the refusal
    names the role that may. A member holds a key to the board — that is not the
    right to decide who else may read it."""
    made = publish(server, owner)
    assert made["board"] == BOARD and made["visibility"] == "public" and made["recorded"]

    again = publish(server, owner)  # an unchanged fact writes NO event
    assert again["visibility"] == "public" and not again["recorded"]

    hers, _ = member(server, tmp_path)
    with pytest.raises(Refused, match="OWNER's move"):
        admin(server, hers, "board.visibility", {"board": BOARD, "visibility": "public"})


def test_a_board_is_private_until_somebody_publishes_it(
    server: BoardServer, owner: str
) -> None:
    """The DEFAULT is the whole model: a board that never heard of this feature —
    every board on the production host — behaves exactly as it always did."""
    assert client(server, BERNA).call("board", {})["visibility"] == "private"
    status, body = anon(server, "board")
    assert status == 409 and "taskops join <url with ?token=" in _prints(body)

    publish(server, owner)
    assert anon(server, "board")[0] == 200
    publish(server, owner, "private")
    assert anon(server, "board")[0] == 409  # and it goes back, the same way


def test_a_visibility_outside_the_pair_is_refused_by_name(
    server: BoardServer, owner: str
) -> None:
    """There is no third state. A typo must never be defaulted — defaulting it
    would leave a board somebody meant to publish quietly private, or worse."""
    with pytest.raises(BadRequest, match="'private' or 'public'"):
        admin(server, owner, "board.visibility", {"board": BOARD, "visibility": "unlisted"})
    assert client(server, BERNA).call("board", {})["visibility"] == "private"


def test_an_admin_argument_that_is_not_text_is_refused_and_never_coerced(
    server: BoardServer, owner: str
) -> None:
    """`scoped.text` REFUSES a non-string, exactly as `verbs/_args.text` does.

    It used to `str()` whatever arrived, and a JSON number survives that intact:
    `{"name": 123}` became the board `"123"` — `mounts.named` allows [a-z0-9-],
    so the name wall could not catch it either. Two doors onto one argument
    shape must not disagree about what an argument is."""
    with pytest.raises(BadRequest, match="this call needs name="):
        admin(server, owner, "board.create", {"name": 123})
    assert "123" not in {b["name"] for b in admin(server, owner, "board.list", {})["boards"]}
    assert not (server.mounts.root / "123").exists()  # and nothing was left behind


def test_a_public_board_answers_every_read_verb_with_no_credential(
    server: BoardServer, owner: str
) -> None:
    """Criterion 1: anonymous sees what a member sees. The board is planned by a
    dev FIRST, so what comes back is real content and not an empty payload that
    would pass whether the gate opened or not."""
    plan(client(server, BERNA))
    publish(server, owner)

    status, body = anon(server, "board")
    assert status == 200
    assert [row["title"] for row in body["data"]["groups"]["take"]] == ["invoice model", "CSV parser"]
    card_id = body["data"]["groups"]["take"][0]["id"]

    assert anon(server, "card", {"task": card_id})[1]["data"]["card"]["spec"] == "the Invoice dataclass"
    assert anon(server, "events", {})[1]["data"]["events"]
    assert anon(server, "report", {})[0] == 200
    # Empty BY CONSTRUCTION: a comment can only name an actor somebody registered,
    # and `anon` is outside the actor grammar, so nothing can ever address it.
    assert anon(server, "mentions", {})[1]["data"]["mentions"] == []


def bearing(httpd: BoardServer, header: str, verb: str = "board") -> tuple[int, Any]:
    """A call carrying an explicit Authorization header, verbatim — the way a
    browser client sends one, including the degenerate shapes a test needs."""
    request = Request(
        f"{url_of(httpd)}/rpc",
        data=json.dumps({"verb": verb, "args": {}}).encode(),
        headers={"Content-Type": "application/json", "Authorization": header},
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            return int(response.status), json.loads(response.read().decode())
    except HTTPError as err:
        with err:  # an HTTPError IS a response: unclosed, it leaks the socket
            return int(err.code), json.loads(err.read().decode())


def test_a_bare_bearer_is_no_credential_and_a_public_board_reads(
    server: BoardServer, owner: str
) -> None:
    """0.5.0's shipped fault: the hosted page sends `"Bearer " + ""`, the header
    arrives as `Bearer`, and `token_in` returned the literal "Bearer" as a
    token — so a PUBLIC board refused its own page with "unknown credential".
    A bearer scheme with no value is NOBODY presenting ANYTHING: it must read
    exactly as the no-header stranger does."""
    plan(client(server, BERNA))
    publish(server, owner)
    for header in ("Bearer", "Bearer ", ""):
        status, body = bearing(server, header)
        assert status == 200, header
        assert body["data"]["groups"]["take"], header


def test_a_bare_bearer_on_a_private_board_refuses_as_no_credential(
    server: BoardServer,
) -> None:
    """No credential is no credential on a private board too — and the sentence
    is the no-credential one (how to join), never "unknown credential"."""
    for header in ("Bearer", "Bearer ", ""):
        status, body = bearing(server, header)
        assert status == 409, header
        assert "taskops join <url with ?token=" in _prints(body), header


def test_a_presented_credential_that_is_wrong_still_refuses_loudly(
    server: BoardServer, owner: str
) -> None:
    """The fix must not widen: once a VALUE was presented — garbage under
    Bearer, or a scheme this server never spoke — there is no anonymous
    fallback, even on a public board, and the sentence does not move."""
    publish(server, owner)
    for header in ("Bearer not-a-token", "Basic dXNlcjpwYXNz"):
        status, body = bearing(server, header)
        assert status == 409, header
        assert "unknown credential" in _prints(body), header


def test_a_real_bearer_value_still_works_and_the_scheme_is_case_insensitive(
    server: BoardServer,
) -> None:
    """RFC 7235: the auth-scheme is case-insensitive. `Bearer <token>` is the
    contract every client already speaks; `bearer <token>` is the same
    credential, not a stranger."""
    token, _ = server.mounts.credentials.mint(BERNA, BOARD, _clock.now())
    for header in (f"Bearer {token}", f"bearer {token}"):
        status, body = bearing(server, header)
        assert status == 200, header
        assert body["ok"] is True, header


def test_the_orchestrators_read_is_not_widened_to_a_stranger(
    server: BoardServer, owner: str
) -> None:
    """`waiting` is the dev's three groups and stays DEV. "Public read" is the
    set of reads the registry marks, not "every verb whose kind is read"."""
    publish(server, owner)
    status, body = anon(server, "waiting")
    assert status == 409 and "orchestrator's moves" in _prints(body)


def test_an_anonymous_write_is_refused_naming_how_a_key_gets_registered(
    server: BoardServer, owner: str
) -> None:
    """Criterion 3, on every write verb there is — and on a PUBLIC board, which
    is the case somebody could think opens a little further. It does not."""
    publish(server, owner)
    for verb in WRITES:
        status, body = anon(server, verb, {"task": "tk-000000"})
        assert status == 409, verb
        message = _prints(body)
        assert "needs a registered key" in message, (verb, message)
        assert "taskops join" in message and "invite" in message, (verb, message)


def test_each_of_the_two_write_walls_stands_on_its_own() -> None:
    """A MUTATION FINDING, and the reason this test exists at all.

    Anonymous is refused a write TWICE: `http/auth.py::anonymous` never hands
    out a credential for a write, and `verbs/__init__.py::call` refuses the role
    at the registry. Over a socket that is defence in depth — and it made both
    guards look pinned while neither was. Deleting the capability check left the
    suite green (the registry caught it); declaring a write verb with WATCHERS
    left it green too (the HTTP door caught it). So each is asserted HERE,
    against its own function, where the other cannot answer for it.
    """
    from taskops import verbs
    from taskops.http import auth
    from taskops.core.types import ANON

    # Wall one: the capability. A public board, a write, no credential.
    with pytest.raises(Refused, match="needs a registered key"):
        auth.anonymous(public=True, need="write")
    assert auth.anonymous(public=True, need="read").subject == ANON
    assert auth.ANONYMOUS.caps == frozenset({"read"})  # it could not carry a write

    # Wall two: the role, with no HTTP anywhere near it. `Stores` is never even
    # opened — `call` refuses on the registry before it touches one.
    stores: Any = None
    for verb, spec in verbs.REGISTRY.items():
        if spec.kind != "write":
            continue
        with pytest.raises(Refused, match="needs a registered key") as refused:
            verbs.call(stores, verb, ANON, {})
        assert "taskops join" in str(refused.value), verb


def test_an_anonymous_write_is_refused_on_a_private_board_too(server: BoardServer) -> None:
    """No credential is no credential: the private board says what it has always
    said, and the sentence a reader learned to recognise does not move."""
    status, body = anon(server, "update", {"task": "tk-000000", "status": "done"})
    assert status == 409 and "taskops join <url with ?token=" in _prints(body)


def test_anonymous_may_not_claim_to_be_somebody(server: BoardServer, owner: str) -> None:
    """The hole this closes: `actor` travels IN the call, so a stranger could
    name `dev:berna` in the body and be judged as him. Anonymous may only ever
    act as anonymous, and the refusal still names the way in."""
    publish(server, owner)
    request = Request(
        f"{url_of(server)}/rpc",
        data=json.dumps({"verb": "board", "actor": BERNA, "args": {}}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(HTTPError) as caught:
        urlopen(request, timeout=5)
    with caught.value as answer:
        assert "may not act as dev:berna" in answer.read().decode()


def test_the_feed_of_a_public_board_opens_with_no_token(
    server: BoardServer, owner: str
) -> None:
    """A message here is a POKE and carries no data (`feed.py`), so a watcher
    learns only that the board moved — and answers by re-reading through /rpc,
    where the anonymous gate applies again in full."""
    with pytest.raises(HTTPError) as refused:
        urlopen(f"{url_of(server)}/feed", timeout=5)
    with refused.value as answer:
        assert answer.code == 409

    publish(server, owner)
    with urlopen(f"{url_of(server)}/feed", timeout=5) as stream:
        assert b"hello" in stream.readline() + stream.readline()


def test_an_anonymous_crawl_of_a_public_board_moves_not_one_byte(
    server: BoardServer, owner: str
) -> None:
    """Criterion 4, and the reason this card exists.

    Every read verb opens with `stores.live.renew(actor, now)` — an INSERT into
    `presence`. A public board without the anon guard would have every visitor
    writing to live.sqlite on every page load: no event, no card, nothing any
    other test would notice. So the assertion is not "no new events" but the
    files themselves, hash for hash, after a crawl that touches every read door
    there is INCLUDING the feed."""
    dev = client(server, BERNA)
    cards = plan(dev)
    worker = client(server, W1, subject=BERNA)
    worker.call("take", {"task": cards[0]["id"]})  # a live lease, to be renewed or not
    publish(server, owner)

    before = _fingerprint(server)
    seen = dict(_presence(server))

    for verb in READS:
        args = {"task": cards[0]["id"]} if verb == "card" else {}
        assert anon(server, verb, args)[0] == 200, verb
    for verb in READS:  # twice: a second crawl is a second chance to write
        assert anon(server, verb, {"task": cards[0]["id"]} if verb == "card" else {})[0] == 200
    with urlopen(f"{url_of(server)}/feed", timeout=5) as stream:
        assert b"hello" in stream.readline() + stream.readline()

    assert _fingerprint(server) == before
    assert dict(_presence(server)) == seen
    assert "anon" not in dict(_presence(server))


def test_the_lease_of_a_live_worker_is_not_renewed_by_a_stranger(
    server: BoardServer, owner: str, clock: Any
) -> None:
    """The subtler half of the same rule, and the one a byte comparison could
    miss if the write ever became an idempotent UPDATE: a visitor reading the
    board must not keep a dead worker's card looking alive. `renew` updates
    every lease held by `actor` — for anon there are none, and it never runs."""
    dev = client(server, BERNA)
    cards = plan(dev)
    worker = client(server, W1, subject=BERNA)
    worker.call("take", {"task": cards[0]["id"]})
    publish(server, owner)
    held = server.mounts.stores(BOARD).live.lease(cards[0]["id"], _clock.now())
    assert held is not None

    clock(60.0)
    for _ in range(5):
        assert anon(server, "board")[0] == 200
    after = server.mounts.stores(BOARD).live.lease(cards[0]["id"], _clock.now())
    assert after is not None and after["expires"] == held["expires"]


def _presence(httpd: BoardServer) -> list[tuple[str, float]]:
    return httpd.mounts.stores(BOARD).live.present(0.0)


# ── the viewer's window: join with nothing, read as nobody ──────────────────


def test_join_with_no_invite_against_a_public_board_is_a_read_only_window(
    server: BoardServer, owner: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Criterion 5, end to end. Nothing is minted, no key is registered, and —
    the part that is easy to miss — the join writes NOTHING on the board either:
    a normal join records this repo's origin as a project event, which for a
    viewer would be the milestone's rule broken by the act of becoming a reader."""
    from taskops.cli import commands

    plan(client(server, BERNA))
    publish(server, owner)
    project = tmp_path / "viewer"
    (project / ".git").mkdir(parents=True)
    monkeypatch.setenv("TASKOPS_ACTOR", "dev:ana")

    before = _fingerprint(server)
    assert commands.join(project, url_of(server), "dev:ana") == 0
    assert _fingerprint(server) == before  # the join itself wrote not one byte

    config = json.loads((project / ".taskops" / "board.json").read_text())
    assert config["url"] == url_of(server) and config["readonly"] is True
    assert json.loads((project / ".taskops" / "remote.json").read_text())["token"] == ""
    assert server.mounts.host.store().principal("ana") is None  # no key registered

    watching = taskops.board.open_board(project, "dev:ana")
    assert [row["title"] for row in watching.call("board", {})["groups"]["take"]][0] == "invoice model"
    with pytest.raises(Refused, match="needs a registered key"):
        watching.call("update", {"task": "tk-000000", "status": "done"})


def test_taskops_ui_serves_a_watchers_window_with_no_credential_anywhere(
    server: BoardServer, owner: str, tmp_path: Path
) -> None:
    """Criterion 5's second half — and a MUTATION FINDING: making `Mounts.public`
    answer False for a bearer-less window left the suite green, because nothing
    exercised the door `taskops ui` actually opens for a viewer.

    Built through `serve()` exactly as `cli/serving.py::ui` builds it for a
    read-only join: an `Upstream` with NO token. The window lets its own browser
    read and forwards the call bare; the REMOTE is what decides, which is why the
    write comes back in the server's own words and not this process's."""
    from tests.test_git import repo
    from taskops.http.upstream import Upstream

    plan(client(server, BERNA))
    publish(server, owner)
    httpd = serve(
        tmp_path / "watcher", "127.0.0.1", 0,
        repo=repo(tmp_path, "watcher-clone"),
        upstream=Upstream(url_of(server), ""),  # the viewer's join: no bearer at all
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{httpd.server_address[1]}/board"
        before = _fingerprint(server)
        status, body = _get_post(base, "", {"verb": "board"})
        assert status == 200, body
        assert [c["title"] for c in body["data"]["groups"]["take"]] == ["invoice model", "CSV parser"]

        status, body = _get_post(base, "", {"verb": "update", "args": {"task": "tk-000000"}})
        assert status == 409 and "needs a registered key" in body["error"]["message"]
        assert _fingerprint(server) == before  # the whole window session, zero bytes
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_a_private_board_refuses_a_join_with_no_invite_exactly_as_today(
    server: BoardServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """And it still names the link it wanted — the refusal a broken paste gets
    has not become "this board is private", which would be a different bug."""
    from taskops.cli import commands

    project = tmp_path / "nope"
    (project / ".git").mkdir(parents=True)
    monkeypatch.setenv("TASKOPS_ACTOR", "dev:ana")
    with pytest.raises(TaskopsError, match="carries no .token= or .invite="):
        commands.join(project, url_of(server), "dev:ana")
    assert not (project / ".taskops" / "board.json").exists()



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


def _redeem(url: str, invite: str, who: str, pubkey: str = "") -> dict[str, Any]:
    from urllib.error import HTTPError
    from urllib.request import Request

    body = {"invite": invite, "who": who}
    if pubkey:
        body["pubkey"] = Path(pubkey).read_text(encoding="utf-8")
    request = Request(
        f"{url}/invite/redeem",
        data=json.dumps(body).encode(),
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


# ── the scp dies: a LOCAL board is promoted to a hosted one ─────────────────
#
# The same real server and the same real keypair as everything above, plus a
# real repo with a real local board on disk. Nothing here stubs the transfer:
# the events cross the socket, the server writes them into its own
# `events.jsonl`, and the assertions are the ones the command itself makes.


def local_repo(tmp_path: Path, name: str = "clone") -> Path:
    """A repo with a LOCAL board in it — what `taskops init` leaves behind."""
    repo = tmp_path / name
    (repo / ".taskops").mkdir(parents=True)
    (repo / ".taskops" / "board.json").write_text("{}\n", encoding="utf-8")
    return seed_local_board(repo)


def seed_local_board(repo: Path) -> Path:
    """The events part of it, alone — a checkout that already exists (the bare
    `board push` test) needs a history in it without a second `.taskops`."""
    from taskops.board import LocalBoard

    board = LocalBoard(repo / ".taskops" / "board", BERNA)
    try:
        cards = plan(board)  # type: ignore[arg-type]  # a LocalBoard is a Board
        board.call("update", {"task": cards[0]["id"], "comment": "before the move"})
    finally:
        board.close()
    return repo


def local_log(repo: Path) -> Path:
    return repo / ".taskops" / "board" / "events.jsonl"


def pushed(target: str, key: Path, invite: str = "") -> int:
    from taskops.cli import push

    return push.run(argparse.Namespace(action="push", target=target, key=str(key), invite=invite))


def test_a_local_board_becomes_the_hosted_one_and_the_config_flips_last(
    server: BoardServer, keyed: Path, owner: str, tmp_path: Path, monkeypatch: Any
) -> None:
    """Criteria 1 and 5, end to end and over a socket: an empty board is created
    on the host, the whole local history is streamed into it, the counts are
    compared — and only then does this repo start reading the remote one, with
    its local board renamed beside itself rather than removed."""
    repo = local_repo(tmp_path)
    mine = local_log(repo).read_text(encoding="utf-8").strip().splitlines()
    admin(server, owner, "board.create", {"name": "promoted"})
    monkeypatch.chdir(repo)

    assert pushed(f"{host_of(server)}/promoted", keyed) == 0

    # The history is THERE, event for event, and the ids are the same ids. Line
    # one is the board's own birth certificate — `board.create` records WHO made
    # it, so the target of a correct push is never literally empty, and the whole
    # local log lands AFTER it (`http/ingest.py::_configuration`).
    theirs = (server.mounts.root / "promoted" / "events.jsonl").read_text(encoding="utf-8")
    lines = theirs.strip().splitlines()
    assert json.loads(lines[0])["body"]["op"] == "created"
    assert [json.loads(line)["id"] for line in lines[1:]] == [
        json.loads(line)["id"] for line in mine
    ]
    assert server.mounts.stores("promoted").head() == len(mine) + 1

    # ONLY NOW the config: the repo reads the server, and it can sign itself in
    # again afterwards, because the `login` block travelled with the flip.
    config = read_config(repo)
    assert config["url"] == f"{host_of(server)}/promoted"
    assert config["login"]["principal"] == "berna" and config["login"]["key"] == str(keyed)
    board = taskops.board.open_board(repo, BERNA)
    assert isinstance(board, RemoteBoard)
    assert [c["title"] for c in board.call("board", {})["groups"]["take"]] == [
        "invoice model",
        "CSV parser",
    ]

    # ARCHIVED, not deleted — the directory it came from still proves what was sent.
    assert not (repo / ".taskops" / "board").exists()
    kept = list((repo / ".taskops").glob("board.local-*"))
    assert len(kept) == 1
    assert (kept[0] / "events.jsonl").read_text(encoding="utf-8").strip().splitlines() == mine


def test_an_interrupted_push_re_runs_to_a_no_op_and_finishes_the_job(
    server: BoardServer, keyed: Path, owner: str, tmp_path: Path, monkeypatch: Any
) -> None:
    """Criterion 2. The interruption is real: half the log is ingested and the
    call never comes back. Re-running sends the WHOLE log again — the ids are
    `sha256` of the content, so the half that landed is recognised, written
    once, and the log on the server has no duplicate line in it."""
    repo = local_repo(tmp_path)
    mine = local_log(repo).read_text(encoding="utf-8").strip().splitlines()
    admin(server, owner, "board.create", {"name": "promoted"})
    half = len(mine) // 2
    stopped = admin(server, owner, "board.ingest", {"board": "promoted", "events": mine[:half]})
    assert stopped["written"] == half and stopped["already_held"] == 0

    monkeypatch.chdir(repo)
    assert pushed(f"{host_of(server)}/promoted", keyed) == 0

    theirs = (server.mounts.root / "promoted" / "events.jsonl").read_text(encoding="utf-8")
    assert theirs.strip().splitlines()[1:] == mine  # no duplicate, no reordering
    assert server.mounts.stores("promoted").head() == len(mine) + 1

    # And a THIRD run, with nothing left to do, is a pure no-op.
    again = admin(server, owner, "board.ingest", {"board": "promoted", "events": mine})
    assert again["written"] == 0 and again["already_held"] == len(mine)
    assert (server.mounts.root / "promoted" / "events.jsonl").read_text(encoding="utf-8") == theirs


def test_a_payload_that_names_one_event_twice_writes_it_once(
    server: BoardServer, owner: str, tmp_path: Path
) -> None:
    """`Stores.write` appends everything it is handed to `events.jsonl` — the
    CACHE ignores a repeated id, the log does not. So the door deduplicates
    against ITSELF as well as against the board, or a payload that named one
    line twice would put two identical lines in the truth and one row in the
    index, and only the log's own reader would ever disagree."""
    repo = local_repo(tmp_path)
    mine = local_log(repo).read_text(encoding="utf-8").strip().splitlines()
    admin(server, owner, "board.create", {"name": "promoted"})

    answer = admin(server, owner, "board.ingest", {"board": "promoted", "events": [*mine, mine[0]]})
    assert answer["received"] == len(mine) + 1
    assert answer["written"] == len(mine)
    assert answer["landed"] == len(mine)  # DISTINCT, read back from the store

    theirs = (server.mounts.root / "promoted" / "events.jsonl").read_text(encoding="utf-8")
    assert theirs.strip().splitlines()[1:] == mine


def test_a_target_that_is_not_empty_is_refused_and_no_force_is_offered(
    server: BoardServer, keyed: Path, owner: str, tmp_path: Path, monkeypatch: Any
) -> None:
    """Criterion 3, and the repo is untouched by the refusal. There is no force
    flag deliberately: two histories would have to be given an order they never
    had, so the refusal says that instead of offering a way to fabricate one."""
    repo = local_repo(tmp_path)
    plan(client(server, BERNA))  # BOARD now has a history of its own
    monkeypatch.chdir(repo)

    with pytest.raises(TaskopsError) as refused:
        pushed(f"{host_of(server)}/{BOARD}", keyed)
    assert "not empty" in str(refused.value)
    assert "no force flag" in str(refused.value)
    assert "board create" in str(refused.value)

    # Step 5 never ran: this is still a local board and still the only copy.
    assert "url" not in read_config(repo)
    assert local_log(repo).exists()
    assert not list((repo / ".taskops").glob("board.local-*"))


def configured(server: BoardServer, name: str, op: str, body: dict[str, Any]) -> None:
    """A project fact written straight onto the target's log — how the host's own
    verbs leave one behind, without a second client having to exist here."""
    from taskops.core.event import make
    from taskops.core.types import PROJECT

    stores = server.mounts.stores(name)
    stores.write([make(PROJECT, "dev:berna", "project", {"op": op, "value": body}, 1786000000.0)])


def worked_on(server: BoardServer, name: str) -> None:
    """ONE card event on the target — the fact that narrows the exemption back
    to the birth certificate and puts the two-histories wall back up."""
    from taskops.core.event import make

    stores = server.mounts.stores(name)
    stores.write([make("tk-0ffff0", "dev:berna", "created", {"card": {"title": "theirs"}}, 1786000000.0)])


def test_a_board_configured_before_it_was_filled_still_accepts_its_push(
    server: BoardServer, keyed: Path, owner: str, tmp_path: Path, monkeypatch: Any
) -> None:
    """THE REPRODUCTION (2026-08-09, promoting this repo's own board): `board
    create` then `board visibility public` and only LATER `board push`. The
    target held two project events, one of them not `created`, and the
    two-histories wall refused a push with nothing to merge. Configuration of a
    container is not a history of work — and the visibility SURVIVES the push,
    which is the user-visible point: the board you made public stays public."""
    repo = local_repo(tmp_path)
    mine = local_log(repo).read_text(encoding="utf-8").strip().splitlines()
    admin(server, owner, "board.create", {"name": "promoted"})
    admin(server, owner, "board.visibility", {"board": "promoted", "visibility": "public"})
    monkeypatch.chdir(repo)

    assert pushed(f"{host_of(server)}/promoted", keyed) == 0

    theirs = (server.mounts.root / "promoted" / "events.jsonl").read_text(encoding="utf-8")
    lines = theirs.strip().splitlines()
    assert [json.loads(line)["body"]["op"] for line in lines[:2]] == ["created", "visibility"]
    assert [json.loads(line)["id"] for line in lines[2:]] == [json.loads(line)["id"] for line in mine]
    assert server.mounts.stores("promoted").head() == len(mine) + 2

    from taskops.verbs.project import visibility

    assert visibility(server.mounts.stores("promoted")) == "public"


def test_a_recorded_remote_is_configuration_too_and_does_not_block_the_push(
    server: BoardServer, keyed: Path, owner: str, tmp_path: Path, monkeypatch: Any
) -> None:
    """The other member of the closed list: `project op=remote` is what
    `gitwork/remote.py` records about the CONTAINER, and it has no order to
    invent against the work either."""
    repo = local_repo(tmp_path)
    mine = local_log(repo).read_text(encoding="utf-8").strip().splitlines()
    admin(server, owner, "board.create", {"name": "promoted"})
    configured(server, "promoted", "remote", {"url": "git@github.com:x/y.git"})
    monkeypatch.chdir(repo)

    assert pushed(f"{host_of(server)}/promoted", keyed) == 0
    assert server.mounts.stores("promoted").head() == len(mine) + 2


def test_a_declared_forge_is_configuration_too_and_does_not_block_the_push(
    server: BoardServer, keyed: Path, owner: str, tmp_path: Path, monkeypatch: Any
) -> None:
    """The op that ARGUED its way into the closed list. Declaring who may reach
    a board is the same act as `visibility` one notch further, and it is done
    to an EMPTY container by definition — nobody opts a board into GitHub after
    filling it and then discovers the push refused."""
    repo = local_repo(tmp_path)
    mine = local_log(repo).read_text(encoding="utf-8").strip().splitlines()
    admin(server, owner, "board.create", {"name": "promoted"})
    configured(
        server, "promoted", "forge", {"host": "github.com", "repo": "x/y", "need": "push"}
    )
    monkeypatch.chdir(repo)

    assert pushed(f"{host_of(server)}/promoted", keyed) == 0
    assert server.mounts.stores("promoted").head() == len(mine) + 2

    from taskops.verbs.project import forge

    assert forge(server.mounts.stores("promoted")) == {
        "host": "github.com",
        "repo": "x/y",
        "need": "push",
    }


def test_one_card_event_on_the_target_puts_the_wall_straight_back_up(
    server: BoardServer, keyed: Path, owner: str, tmp_path: Path, monkeypatch: Any
) -> None:
    """The wall does not move an inch. Created AND configured is exempt; created,
    configured and WORKED ON is two histories, and the refusal is today's."""
    repo = local_repo(tmp_path)
    admin(server, owner, "board.create", {"name": "promoted"})
    admin(server, owner, "board.visibility", {"board": "promoted", "visibility": "public"})
    worked_on(server, "promoted")
    monkeypatch.chdir(repo)

    with pytest.raises(TaskopsError) as refused:
        pushed(f"{host_of(server)}/promoted", keyed)
    # The visibility event stops being exempt as well — TWO events it never observed.
    assert "already holds 2 event(s) this push never observed" in str(refused.value)
    assert "no force flag" in str(refused.value)
    assert "url" not in read_config(repo)


def test_a_project_op_outside_the_closed_list_still_refuses_the_push(
    server: BoardServer, keyed: Path, owner: str, tmp_path: Path, monkeypatch: Any
) -> None:
    """The list is CLOSED on purpose: an op added later must argue its way into
    `_configuration` rather than fall in because it happens to be board-level."""
    repo = local_repo(tmp_path)
    admin(server, owner, "board.create", {"name": "promoted"})
    configured(server, "promoted", "archived", {"why": "a fact this list never judged"})
    monkeypatch.chdir(repo)

    with pytest.raises(TaskopsError) as refused:
        pushed(f"{host_of(server)}/promoted", keyed)
    assert "already holds 1 event(s) this push never observed" in str(refused.value)


def test_a_board_somebody_is_working_on_is_not_pushed(
    server: BoardServer, keyed: Path, owner: str, tmp_path: Path, monkeypatch: Any
) -> None:
    """Step 2. Leases do not travel — `live.sqlite` is a fact about processes
    that are running, and none of them will be running against the new host. So
    the check is not "copy them", it is "there must be none to lose"."""
    from taskops.board import LocalBoard

    repo = local_repo(tmp_path)
    admin(server, owner, "board.create", {"name": "promoted"})
    board = LocalBoard(repo / ".taskops" / "board", W1)
    try:
        card = [c for c in board.call("board", {})["groups"]["take"]][0]
        board.call("take", {"task": card["id"]})
    finally:
        board.close()
    monkeypatch.chdir(repo)

    with pytest.raises(TaskopsError, match="holding a lease"):
        pushed(f"{host_of(server)}/promoted", keyed)
    assert server.mounts.stores("promoted").head() == 1  # its birth event, and nothing else
    assert "url" not in read_config(repo)


def test_ingest_is_owner_or_member_only_and_says_how_a_key_gets_registered(
    server: BoardServer, owner: str, tmp_path: Path
) -> None:
    """The door is server scope like every other admin verb — an unkeyed caller
    is refused naming the way in, which is this milestone's house rule."""
    admin(server, owner, "board.create", {"name": "promoted"})
    stray, _ = server.mounts.credentials.mint(BERNA, BOARD, _clock.now())  # a BOARD token
    with pytest.raises(Refused) as refused:
        admin(server, stray, "board.ingest", {"board": "promoted", "events": ["{}"]})
    assert "taskops join" in str(refused.value)
    assert server.mounts.stores("promoted").head() == 1  # only the board's own birth


def test_ingest_is_refused_to_a_principal_whose_key_this_host_never_registered(
    server: BoardServer, keyed: Path, owner: str
) -> None:
    """The ROLE gate, and it is a different wall from the one above: this
    credential IS server-scoped, so it reaches `core/scope.py::permit` — which
    finds no key for the principal, calls it `anon`, and refuses naming how a key
    gets registered. Without the gate, a `*` token would be enough to move a
    history onto somebody else's host."""
    admin(server, owner, "board.create", {"name": "promoted"})
    stray, _ = server.mounts.credentials.mint("dev:mallory", "*", _clock.now())
    with pytest.raises(Refused) as refused:
        admin(server, stray, "board.ingest", {"board": "promoted", "events": ["{}"]})
    assert "anon may not board.ingest" in str(refused.value)
    assert "taskops server key add" in str(refused.value)
    assert server.mounts.stores("promoted").head() == 1


def test_a_short_push_stops_before_the_config_flips(
    server: BoardServer, keyed: Path, owner: str, tmp_path: Path, monkeypatch: Any
) -> None:
    """Step 4, against a push that really is short — one event is dropped on the
    way out, exactly as a truncated scp used to drop them. The counts disagree,
    the command STOPS, and this repo is still the local board it was: without
    the comparison the promotion would have reported success and lost an event."""
    from taskops.cli import push as promote

    repo = local_repo(tmp_path)
    mine = local_log(repo).read_text(encoding="utf-8").strip().splitlines()
    admin(server, owner, "board.create", {"name": "promoted"})
    monkeypatch.chdir(repo)

    honest = promote.operate.call

    def short(host: str, verb: str, args: dict[str, Any], token: str = "") -> dict[str, Any]:
        args = {**args, "events": list(args["events"])[:-1]} if verb == "board.ingest" else args
        return honest(host, verb, args, token)

    monkeypatch.setattr(promote.operate, "call", short)
    with pytest.raises(TaskopsError) as stopped:
        pushed(f"{host_of(server)}/promoted", keyed)
    assert "did not come back with what was sent" in str(stopped.value)
    assert f"local {len(mine):>6}   remote {len(mine) - 1:>6}" in str(stopped.value)

    assert "url" not in read_config(repo)
    assert local_log(repo).exists()
    assert not list((repo / ".taskops").glob("board.local-*"))


def test_ingest_refuses_a_line_that_does_not_match_its_own_content(
    server: BoardServer, owner: str, tmp_path: Path
) -> None:
    """The door verifies the HASH and nothing else — it does not re-judge events
    the verbs already validated. A tampered line lands nowhere, and the ones
    beside it do not land either: the whole call is refused."""
    repo = local_repo(tmp_path)
    mine = local_log(repo).read_text(encoding="utf-8").strip().splitlines()
    admin(server, owner, "board.create", {"name": "promoted"})
    forged = json.loads(mine[0])
    forged["actor"] = "dev:mallory"
    with pytest.raises(BadRequest, match="does not match its own content"):
        admin(
            server,
            owner,
            "board.ingest",
            {"board": "promoted", "events": [json.dumps(forged), *mine[1:]]},
        )
    assert server.mounts.stores("promoted").head() == 1  # only the board's own birth


def test_a_push_into_a_board_nobody_created_says_which_command_makes_one(
    server: BoardServer, keyed: Path, tmp_path: Path, monkeypatch: Any
) -> None:
    """`Mounts.stores` never creates — so the refusal has to name the door that
    does, or the only way to learn it is to read the source."""
    repo = local_repo(tmp_path)
    monkeypatch.chdir(repo)
    with pytest.raises(NotFound, match="taskops board create"):
        pushed(f"{host_of(server)}/nobodys", keyed)
    assert "url" not in read_config(repo)


# ── and join stops orphaning the board that is already here ────────────────


def test_join_refuses_to_orphan_a_local_board_and_names_both_ways_out(
    server: BoardServer, tmp_path: Path
) -> None:
    """Criterion 4. Before this, joining simply started reading the remote board:
    the local history stayed on disk, byte for byte, and nothing ever looked at
    it again or said so. The command that made it invisible was a command about
    connecting, and nobody was told."""
    from taskops.cli import commands

    repo = local_repo(tmp_path)
    token, _ = server.mounts.credentials.mint(BERNA, BOARD, _clock.now())
    url = f"{url_of(server)}?token={token}"

    with pytest.raises(TaskopsError) as refused:
        commands.join(repo, url, BERNA)
    assert "board push" in str(refused.value)
    assert "--discard-local" in str(refused.value)
    assert "url" not in read_config(repo)  # nothing was written by the refusal
    assert local_log(repo).exists()


def test_discard_local_archives_the_board_it_replaces_and_deletes_nothing(
    server: BoardServer, tmp_path: Path
) -> None:
    """Criterion 4's other half — and the archive is the same rename `push`
    does, because it is the same moment seen from the other side."""
    from taskops.cli import commands

    repo = local_repo(tmp_path)
    mine = local_log(repo).read_text(encoding="utf-8")
    token, _ = server.mounts.credentials.mint(BERNA, BOARD, _clock.now())

    assert commands.join(repo, f"{url_of(server)}?token={token}", BERNA, discard=True) == 0

    assert read_config(repo)["url"] == url_of(server)
    assert not (repo / ".taskops" / "board").exists()
    kept = list((repo / ".taskops").glob("board.local-*"))
    assert len(kept) == 1 and (kept[0] / "events.jsonl").read_text(encoding="utf-8") == mine


def test_an_empty_local_board_is_not_something_to_orphan(
    server: BoardServer, tmp_path: Path
) -> None:
    """`taskops init` then `taskops join` is an ordinary sequence, and the
    guardrail counts EVENTS, not the directory: an empty history has nothing to
    lose, so refusing on it would cost a real workflow and buy nothing."""
    from taskops.cli import commands

    repo = tmp_path / "fresh"
    (repo / ".taskops" / "board").mkdir(parents=True)
    (repo / ".taskops" / "board.json").write_text("{}\n", encoding="utf-8")
    token, _ = server.mounts.credentials.mint(BERNA, BOARD, _clock.now())

    assert commands.join(repo, f"{url_of(server)}?token={token}", BERNA) == 0
    assert read_config(repo)["url"] == url_of(server)
    assert not list((repo / ".taskops").glob("board.local-*"))


# ── COMPAT: production's exact state, proven and not assumed ────────────────
#
# The chapter's third rule — EXISTING BEARER TOKENS KEEP WORKING — protects four
# real boards on `taskops.bernardocastro.dev`. Their shape is not merely "a board
# with a token"; it is a host that knows NOTHING this chapter added: no
# principal, no pubkey, no `allowed_signers` file, and a `remote.json` exactly
# one key long. Every test above this line arrives at that state incidentally
# (`client()` mints a bearer). These arrive at it ON PURPOSE — through the real
# on-box `taskops invite --root <dir>`, redeemed with no key, which is literally
# how production's credentials came to exist — then ASSERT it is that state, and
# only then drive the four doors a production board is actually used through:
# /rpc, /feed, the MCP handshake, and the `taskops ui` window's forwarded /rpc.


@pytest.fixture()
def legacy(server: BoardServer, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> str:
    """A standing bearer, minted by the ON-BOX command and read off its own
    output — not from the store behind it. If `taskops invite --root` ever
    stopped printing a redeemable URL, this fixture would fail rather than
    quietly test a token no human could have obtained."""
    from taskops.cli import admin

    admin.on_box_invite(tmp_path / "boards", "berna", BOARD)
    printed = capsys.readouterr().out
    invite = printed.partition("?invite=")[2].strip()
    assert invite, printed
    return str(_redeem(url_of(server), invite, "berna")["token"])


def _untouched_host(server: BoardServer, tmp_path: Path) -> None:
    """The precondition, spelled out: this host has learned nothing new. A
    keyless join enrols nobody, so there is no principal and no key — and
    `allowed_signers`, the file `ssh-keygen -Y verify` consumes, is EMPTY.

    Empty and not absent, which is the honest statement and was found by this
    test failing on the stricter one: `ServerStore.__init__` regenerates the
    file whenever the store is opened, so merely starting a server creates it.
    That is not a hole — the file is derived WHOLE from the principals table, so
    zero principals means zero signers, and `-Y verify` against it refuses
    everybody. Asserting its emptiness pins the property that matters; asserting
    its absence would have pinned a startup detail instead."""
    from taskops.store.server import ServerStore

    store = ServerStore(tmp_path / "boards")
    try:
        assert store.principals() == [] and store.keys() == []
    finally:
        store.close()
    assert (tmp_path / "boards" / "allowed_signers").read_text(encoding="utf-8") == ""


def test_a_legacy_only_board_still_works_on_rpc(
    server: BoardServer, tmp_path: Path, legacy: str
) -> None:
    """Door 1. The whole cycle — plan, assign, take, bind, done, merged — on a
    credential with no principal behind it, exactly as production's four run."""
    _untouched_host(server, tmp_path)

    dev = RemoteBoard(url_of(server), legacy, BERNA)
    cards = plan(dev)
    dev.call("assign", {"tasks": [cards[0]["id"]]})
    worker = RemoteBoard(url_of(server), legacy, W1)  # dev credential, its own agent
    worker.call("take", {"task": cards[0]["id"]})
    worker.call("bind", {"task": cards[0]["id"], "sha": "a1b2", "subject": "feat: model"})
    worker.call("update", {"task": cards[0]["id"], "status": "done", "comment": "done"})
    assert dev.call("merged", {"task": cards[0]["id"], "sha": "9c2f"})["into"] == "ms/mvp-facturador"

    _untouched_host(server, tmp_path)  # and a full cycle enrolled nobody


def test_a_legacy_token_still_opens_the_feed(
    server: BoardServer, tmp_path: Path, legacy: str
) -> None:
    """Door 2. `?token=` on /feed is how every joined clone watches, and the
    anonymous gate added this chapter sits in front of it — a private board with
    a standing bearer must pass it untouched."""
    _untouched_host(server, tmp_path)
    with urlopen(f"{url_of(server)}/feed?token={legacy}", timeout=5) as stream:
        assert b"hello" in stream.readline() + stream.readline()


def test_a_legacy_config_opens_the_MCP_board_and_its_handshake(
    server: BoardServer, tmp_path: Path, legacy: str
) -> None:
    """Door 3, and the one with the most moving parts under it. The MCP server
    opens a board from `remote.json` and renders the panorama INTO the handshake
    (`mcp/hello.py`). A config with no `login` block must reach that far with no
    refresh attempted — `hello` swallows every TaskopsError, so a broken legacy
    path would not raise here, it would silently hand back an EMPTY panorama."""
    from taskops.mcp import hello
    from taskops.board import open_board
    from taskops.gitwork import install
    from taskops.mcp.server import INSTRUCTIONS

    plan(RemoteBoard(url_of(server), legacy, BERNA))
    project = tmp_path / "clone"
    install.write_config(project, url_of(server), legacy)
    assert json.loads((project / ".taskops" / "remote.json").read_text()) == {"token": legacy}

    handshake = hello.hello(open_board(project, BERNA), INSTRUCTIONS)
    assert "invoice model" in handshake["instructions"]  # the panorama, not silence
    _untouched_host(server, tmp_path)


def test_the_two_branches_of_answered_agree_on_who_gets_poked(
    server: BoardServer, window: BoardServer
) -> None:
    """PARITY, pinned as a class and not as one bug.

    `rpc.answered` forks on `upstream`: a board this process owns is dispatched
    locally, somebody else's is relayed. The two branches must agree about the
    questions that are the SAME question on both sides — and the infinite loop
    happened because one of them silently did not: the local branch asked
    `writes()` before poking the page and the forwarded branch never did.

    Nothing in the type system, the linter or any single-branch test could see
    that, because each branch was correct on its own terms. So the parity is
    asserted directly, verb by verb, over the whole registry: for every verb,
    a LOCAL call and a FORWARDED call must reach the same verdict on whether the
    page is told the board moved. A step added to one branch and forgotten in
    the other now goes red here, whatever the step is."""
    local, remote = [], []
    server.mounts.hub.publish = lambda board, message: local.append(message["verb"])  # type: ignore[method-assign]
    window.mounts.hub.publish = lambda board, message: remote.append(message["verb"])  # type: ignore[method-assign]

    direct = client(server, BERNA)
    through = RemoteBoard(url_of(window), _token(window, BERNA), BERNA)
    plan(direct)  # a card to read and a card to write on, on the one board both see
    task = direct.call("board", {})["groups"]["take"][0]["id"]

    for verb, args in (
        ("board", {}),
        ("card", {"task": task}),
        ("events", {"limit": 1}),
        ("report", {"window": "1d"}),
        ("update", {"task": task, "comment": "a write both branches must announce"}),
    ):
        # One branch at a time, or the bookkeeping lies: a FORWARDED write also
        # reaches the host, whose own local branch pokes there too. What is
        # being compared is the decision each branch takes about ITS listeners.
        local.clear()
        direct.call(verb, dict(args))
        by_local = list(local)

        remote.clear()
        through.call(verb, dict(args))
        by_forward = list(remote)

        assert by_local == by_forward, (
            f"{verb!r} pokes differently depending on which side answered: "
            f"local={by_local} forwarded={by_forward}"
        )


def test_a_forwarded_READ_pokes_nobody_so_a_window_cannot_feed_itself(
    server: BoardServer, window: BoardServer
) -> None:
    """The infinite loop, pinned. Every envelope carries `seq`, so the forwarded
    path's old `if status == 200 and seq` was true of every READ: a `board` call
    published "the board changed", the page believed the frame and refetched, and
    that refetch published again. A window on a REMOTE board hammered its own
    server at the coalescing interval, forever, with nothing on the board moving —
    measured at ~5 requests/second against a board whose seq never left 961.

    The local path never had it because it asks `writes()` first; this asserts the
    forwarded half asks the same question of the same registry."""
    published: list[dict[str, Any]] = []
    window.mounts.hub.publish = lambda board, message: published.append(message)  # type: ignore[method-assign]

    plan(client(server, BERNA))  # something real to read, so seq is non-zero
    viewer = RemoteBoard(url_of(window), _token(window, BERNA), BERNA)
    for _ in range(3):
        assert viewer.call("board", {})["seq"] > 0
        viewer.call("events", {"limit": 1})
    assert published == [], f"a read poked the page: {published}"

    task = viewer.call("board", {})["groups"]["take"][0]["id"]
    viewer.call("update", {"task": task, "comment": "a write, and this one IS news"})
    assert [m["verb"] for m in published] == ["update"]


def test_the_ui_window_forwards_with_a_legacy_token(
    server: BoardServer, tmp_path: Path, legacy: str
) -> None:
    """Door 4. `taskops ui` against a remote board forwards /board/rpc upstream
    with the bearer out of `remote.json` (`http/upstream.py`). That bearer is a
    standing legacy one on all four production boards, so the window is built
    here exactly as `cli/serving.py` builds it — around `legacy` and nothing
    else — and asked for the cards the SERVER holds."""
    from tests.test_git import repo
    from taskops.http.upstream import Upstream

    plan(RemoteBoard(url_of(server), legacy, BERNA))
    httpd = serve(
        tmp_path / "window",
        "127.0.0.1",
        0,
        repo=repo(tmp_path, "viewer"),
        upstream=Upstream(url_of(server), legacy),
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{httpd.server_address[1]}/board"
        token, _ = httpd.mounts.credentials.mint(BERNA, "board", _clock.now())
        body = _post(url, token, {"verb": "board", "actor": BERNA})
        assert body["ok"] is True
        titles = [c["title"] for c in body["data"]["groups"]["take"]]
        assert titles == ["invoice model", "CSV parser"]
    finally:
        httpd.shutdown()
        httpd.server_close()
    _untouched_host(server, tmp_path)


# ── the owner's `gh`: WHERE a GitHub token may come from ─────────────────────
#
# What is left of the block that pinned the dev-side GitHub flag this chapter
# deleted. The flow tests went with the flag; the rule about
# the TOKEN did not, because `board forge` still reads one — on the OWNER's
# machine, for one command. Kept as a tail block for the reason it was written
# as one: parallel worktrees merge two tails cleanly and interleaved edits not
# at all. Every import below is local for the same reason.
#
# The `gh` these tests run is a REAL executable on a REAL PATH: `gh auth token`
# failing, printing nothing, or not existing are three different things, and
# monkeypatching the call away would test none of them. It also keeps the suite
# off the machine's own gh, whose answer would be somebody's actual token.


def fake_gh(where: Path, prints: str = "", code: int = 0) -> Path:
    """A `gh` on PATH that records the arguments it was called with."""
    import os
    import stat

    where.mkdir(parents=True, exist_ok=True)
    seen = where / "gh-was-asked"
    script = where / "gh"
    script.write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> "{seen}"\n'
        f"if [ {code} -eq 0 ]; then printf '%s\\n' '{prints}'; "
        f"else printf '%s\\n' '{prints}' >&2; fi\n"
        f"exit {code}\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    os.environ.setdefault("PATH", "")
    return seen


def on_path(monkeypatch: pytest.MonkeyPatch, where: Path) -> None:
    import os

    monkeypatch.setenv("PATH", f"{where}{os.pathsep}{os.environ.get('PATH', '')}")


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """A checkout named after the board, so the BARE join can find it later."""
    where = tmp_path / "clone" / BOARD
    (where / ".git").mkdir(parents=True)
    return where

def test_the_token_is_gh_then_the_environment_then_a_HIDDEN_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three sources, in one order, and the fourth that must never exist.

    `gh` wins while it answers, because the machine of anybody with push on the
    repo already has it authenticated and the common case must ask nothing.

    It MOVED to `cli/github.py` when `board forge` grew a second caller for it —
    the order, the hidden prompt and the flag that must never exist are the
    contract and are unchanged; only the module holding them is."""
    import getpass as getpass_module

    from taskops.cli import github as asking

    monkeypatch.setenv("GITHUB_TOKEN", "from-the-environment")
    monkeypatch.setattr(getpass_module, "getpass", _refuse_to_prompt)
    asked = fake_gh(tmp_path / "bin", prints=TOKEN)
    on_path(monkeypatch, tmp_path / "bin")
    assert asking.token() == TOKEN
    assert asked.read_text(encoding="utf-8").strip() == "auth token"

    # `gh` there but not logged in: the environment answers, and nothing prompts.
    fake_gh(tmp_path / "bin", prints="not logged into any GitHub hosts", code=1)
    assert asking.token() == "from-the-environment"

    # Neither: a HIDDEN prompt — getpass, never input(), which would echo the
    # token into the terminal and into anything scraping the session.
    monkeypatch.delenv("GITHUB_TOKEN")
    monkeypatch.setattr("builtins.input", _refuse_to_prompt)
    monkeypatch.setattr(getpass_module, "getpass", lambda *_: f"  {TOKEN}\n")
    assert asking.token() == TOKEN

    # And typing nothing at it is a refusal that names all three ways in.
    monkeypatch.setattr(getpass_module, "getpass", lambda *_: "")
    with pytest.raises(TaskopsError) as refused:
        asking.token()
    for way in ("gh auth login", "GITHUB_TOKEN", "hidden prompt"):
        assert way in str(refused.value)
    assert "No flag takes a token" in str(refused.value)


def _refuse_to_prompt(*_: Any, **__: Any) -> str:
    raise AssertionError("a token was already available — this must not have prompted")


def test_no_flag_on_join_takes_a_token_and_none_ever_will(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The rule that outlived the flag it was written for, pinned at the parser.

    A secret passed as an argument is written to the shell's history file before
    the process starts and sits in `ps` for every user on the box while it runs,
    so the only safe design is the one with no place to put it. There used to be
    a `store_true` here whose whole feature was taking no value; now `join` has
    no GitHub surface at all, which is the same guarantee with less to get
    wrong — and this asserts the ABSENCE, because a flag that quietly came back
    taking a value is exactly how the rule would be lost.
    """
    from taskops.cli.main import main

    with pytest.raises(SystemExit):
        main(["join", "--help"])
    printed = capsys.readouterr().out
    assert "--invite" in printed  # the positive control: this really read the join parser
    assert "github" not in printed.lower()

    # argparse renders every flag it accepts into that text, so a flag reaching
    # for a token cannot be merely undocumented here: an argv naming one is an
    # unknown option, exit 2, with the would-be secret never consumed.
    gone = "--" + "git" + "hub"  # spelled apart on purpose: the repo greps for it
    with pytest.raises(SystemExit) as exited:
        main(["join", "some-board", gone, "ghp_never_in_history"])
    assert exited.value.code == 2
    assert "ghp_never_in_history" in capsys.readouterr().err  # and nothing ran


# ── /git/file — a committed REPORT, from the reader's own clone ─────────────
#
# The reports chapter puts the narration in git and a POINTER on the board, so
# the bytes have to come from somewhere: this door, over the same token and the
# same envelope as every other. Which makes it the one door that takes a PATH
# from a browser, and every test below is about the wall in front of it —
# `core/reports.py::under()`, the same call the verb that registers a report
# makes, so the two ends cannot drift.


REPORT = ".taskops/reports/ms-6f7a24-first.html"
SECRET = "secrets.env"


@pytest.fixture()
def reports_server(tmp_path: Path) -> Iterator[BoardServer]:
    """A host inside a checkout that carries a committed report — and, one
    directory up from it, something nobody may ever be handed."""
    from tests.test_git import repo
    from taskops.gitwork import run

    root = repo(tmp_path, "narrated")
    (root / SECRET).write_text("TOKEN=hunter2\n", encoding="utf-8")
    (root / ".taskops" / "reports").mkdir(parents=True)
    (root / REPORT).write_text("<h1>the chapter</h1>\n", encoding="utf-8")
    (root / ".taskops" / "reports" / "notes.md").write_text("# plain\n", encoding="utf-8")
    # A type the door has NEVER been taught, and the point of the fixture: `.md`
    # used to play this part and stopped being unknown the day it got a renderer.
    (root / ".taskops" / "reports" / "notes.rst").write_text("plain\n", encoding="utf-8")
    run.must("add", "-A", cwd=root)
    run.must("commit", "-q", "-m", "the report", cwd=root)
    httpd = serve(tmp_path / "boards", "127.0.0.1", 0, repo=root)
    httpd.mounts.create(BOARD)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def _file(httpd: BoardServer, path: str, rev: str = "HEAD") -> tuple[int, dict[str, Any]]:
    from urllib.parse import quote

    url = f"{url_of(httpd)}/git/file/{rev}?path={quote(path, safe='')}"
    return _get(url, _token(httpd, BERNA))


def test_the_door_hands_back_one_committed_report_at_a_rev(
    reports_server: BoardServer,
) -> None:
    """The whole point of the door: a reader renders the report from its OWN
    clone, at the sha the event named, and `events.jsonl` never carried a byte
    of it. The rev comes back RESOLVED — 40 hex — because that sha is what the
    UI keys and refetches on, never the word the browser happened to send."""
    status, body = _file(reports_server, REPORT)
    assert status == 200 and body["ok"] is True
    data = body["data"]
    assert data["text"] == "<h1>the chapter</h1>"
    assert data["path"] == REPORT
    assert len(data["rev"]) == 40 and set(data["rev"]) <= set("0123456789abcdef")
    assert data["content_type"] == "text/html"
    assert data["truncated"] is False and data["cap"] > 0


def test_only_a_literal_html_report_is_typed_as_html(
    reports_server: BoardServer,
) -> None:
    """A type the door does not know degrades to TEXT, never to something a
    renderer would execute — and the type is a field in a JSON envelope, so no
    path can make this origin, where the token lives, serve HTML itself.

    The example used to be `notes.md`, and this test failed the day markdown got
    a renderer. The CLAIM did not change and is not weakened here: an unknown
    type still degrades, and `.html` is still the only thing typed as HTML — the
    file standing for "unknown" is just one the door genuinely does not know,
    since `.md` no longer is. The type it did gain is asserted right below, so
    the pair says what the door answers for all three shapes."""
    status, body = _file(reports_server, ".taskops/reports/notes.rst")
    assert status == 200 and body["data"]["content_type"] == "text/plain"
    status, body = _file(reports_server, ".taskops/reports/" + REPORT.rpartition("/")[2])
    assert status == 200 and body["data"]["content_type"] == "text/html"


def test_a_markdown_report_is_typed_as_markdown_and_never_as_html(
    reports_server: BoardServer,
) -> None:
    """Prose gets its own type so the READER can draw it as prose. It is not a
    third security case and must never become one: `text/markdown` is drawn by
    the dashboard's own renderer, which builds React elements and emits no HTML
    (`ReportFrame.tsx`), so it needs no sandbox — and it is emphatically not
    `text/html`, which is the type that does."""
    status, body = _file(reports_server, ".taskops/reports/notes.md")
    assert status == 200
    assert body["data"]["content_type"] == "text/markdown"
    assert body["data"]["content_type"] != "text/html"


def test_every_path_that_is_not_a_report_is_refused_and_nothing_leaks(
    reports_server: BoardServer,
) -> None:
    """The security boundary, one path per shape it can arrive in. The traversals
    matter most: `under()` REFUSES them rather than normalising them, so a path
    that would resolve to a real file outside the directory never reaches git.

    The `..` cases are checked twice — refused, AND the secret's contents absent
    from the whole answer — because a door that refused with the file quoted in
    its message would still have leaked it."""
    for path in (
        SECRET,  # a real file, in the repo, one directory up
        "../narrated/" + SECRET,
        ".taskops/reports/../../" + SECRET,
        ".taskops/reports/../" + SECRET,
        "/etc/passwd",
        "/" + REPORT,
        ".taskops/reports//ms-6f7a24-first.html",  # a doubled separator
        ".taskops/reports",  # the directory itself
        ".taskops/reports/",
        ".taskops/reportsX/evil.html",  # a prefix that only LOOKS like the dir
        "",  # no ?path= at all
    ):
        status, body = _file(reports_server, path)
        message = body["error"]["message"]
        assert status == 400 and body["ok"] is False, f"{path} was not refused"
        assert ".taskops/reports/" in message and "not a file server" in message
        assert "hunter2" not in json.dumps(body), f"{path} leaked the file"


def test_a_report_path_git_could_not_be_shown_is_its_own_refusal(
    reports_server: BoardServer,
) -> None:
    """The second wall, and it says a different thing than the first: this IS
    under the reports directory, and it is still refused — `diff.usable`, the one
    shape guard everything handed to git passes. Its own words, because "not a
    report" would be a lie about a file sitting right there."""
    status, body = _file(reports_server, ".taskops/reports/a report.html")
    assert status == 400 and body["ok"] is False
    assert "not a shape this door shows git" in body["error"]["message"]
    assert "Rename the file" in body["error"]["message"]


def test_a_report_is_served_from_the_COMMIT_never_the_working_copy(
    reports_server: BoardServer, tmp_path: Path,
) -> None:
    """`git show <sha>:<path>` reads a tree entry, not the disk. A report is
    quoted at the sha its event names, so a checkout that has moved on — or a
    file since deleted — still renders exactly what was registered."""
    disk = tmp_path / "narrated" / REPORT
    disk.write_text("<h1>rewritten since</h1>\n", encoding="utf-8")
    status, body = _file(reports_server, REPORT)
    assert status == 200 and body["data"]["text"] == "<h1>the chapter</h1>"
    disk.unlink()
    status, body = _file(reports_server, REPORT)
    assert status == 200 and body["data"]["text"] == "<h1>the chapter</h1>"


def test_a_rev_this_clone_lacks_reads_as_a_fetch_nobody_ran(
    reports_server: BoardServer,
) -> None:
    """The same refusal the diff doors give, from the same `_stale` — a report
    registered by another dev names a commit this clone may not have yet, and
    that is not an error, it is the truth about this disk."""
    status, body = _file(reports_server, REPORT, rev="tk-91a27e")
    assert status == 404 and "not in your clone yet" in body["error"]["message"]
    assert "git fetch origin tk-91a27e" in body["error"]["message"]


def test_a_commit_that_does_not_carry_the_report_says_exactly_that(
    reports_server: BoardServer,
) -> None:
    """Distinct from both other refusals: the rev resolved and the path is a
    report — this commit simply predates the file. Saying so is what tells a
    reader the event's sha is the one to ask for."""
    status, body = _file(reports_server, REPORT, rev="HEAD~1")
    assert status == 404 and body["ok"] is False
    assert "does not carry that file" in body["error"]["message"]


def test_an_over_cap_report_comes_back_flagged_with_the_cap_stated(
    reports_server: BoardServer, tmp_path: Path,
) -> None:
    """A silently cut file is a lie, a flagged one is a fact — `patch()`'s idiom,
    on the same constant, which is why `capped()` is one function and not two."""
    from taskops.gitwork import run, patch

    big = ".taskops/reports/ms-6f7a24-huge.html"
    root = tmp_path / "narrated"
    (root / big).write_text("<p>" + "x" * (patch.CAP + 1000) + "</p>\n", encoding="utf-8")
    run.must("add", "-A", cwd=root)
    run.must("commit", "-q", "-m", "a huge report", cwd=root)
    status, body = _file(reports_server, big)
    assert status == 200
    data = body["data"]
    assert data["truncated"] is True and data["cap"] == patch.CAP
    assert len(data["text"].encode()) <= patch.CAP


def test_a_host_that_serves_boards_mounts_no_file_door_either(
    server: BoardServer,
) -> None:
    """The switch is `Mounts.repo`, decided once at construction: `taskops serve`
    has no clone, so /git is 404 whole — a new question underneath it does not
    open a door the host never mounted."""
    assert server.mounts.repo is None
    status, body = _get(f"{url_of(server)}/git/file/HEAD?path={REPORT}", _token(server, BERNA))
    assert status == 404 and "not a repository" in body["error"]["message"]


def test_the_file_door_is_the_same_token_door_as_the_rest(
    reports_server: BoardServer,
) -> None:
    """No second credential system, and no read-only exception for prose."""
    with pytest.raises(HTTPError) as caught:
        urlopen(f"{url_of(reports_server)}/git/file/HEAD?path={REPORT}", timeout=5)
    assert json.loads(caught.value.read().decode())["error"]["code"] == "refused"


# ── and the lifecycle runs backwards: `taskops board pull` ──────────────────
#
# The same real server, the same real keypair and the same socket as the push
# tests above — read in the other direction. Nothing here stubs the transfer:
# the events are paged down through the `events` verb, written through
# `Stores`, and the assertions compare the two logs BY ID.


def pulled(target: str = "", key: str = "") -> int:
    from taskops.cli import pull

    return pull.run(argparse.Namespace(action="pull", target=target, key=key, principal=""))


def host_log(httpd: BoardServer, name: str = BOARD) -> str:
    """The host's own truth, on the host's own disk — read back after a pull to
    prove the command took nothing away."""
    return (httpd.mounts.root / name / "events.jsonl").read_text(encoding="utf-8")


def ids_in(text: str) -> list[str]:
    return [json.loads(line)["id"] for line in text.strip().splitlines()]


def test_a_hosted_board_comes_down_whole_and_the_host_keeps_every_byte(
    server: BoardServer, joined: Path
) -> None:
    """Criterion 1, end to end and over a socket: the whole history lands here,
    every id is accounted for, the config flips LAST — and the board on the
    server is byte for byte what it was, because a pull destroys nothing."""
    from taskops.cli.main import main

    plan(client(server, BERNA))
    before = host_log(server)

    assert main(["board", "pull", f"{host_of(server)}/{BOARD}"]) == 0

    # Event for event, by ID, in the order the host holds them.
    assert ids_in(local_log(joined).read_text(encoding="utf-8")) == ids_in(before)
    # The HOST is read back: same bytes, same head. This is the milestone's rule.
    assert host_log(server) == before
    assert server.mounts.stores(BOARD).head() == len(ids_in(before))

    # ONLY NOW the config — and only `board.json`. `remote.json` keeps its login,
    # so `board create` / `board push` still know which server to go to.
    config = read_config(joined)
    assert "url" not in config
    assert config["login"]["host"] == host_of(server) and config["token"]
    board = taskops.board.open_board(joined, BERNA)
    assert isinstance(board, taskops.board.LocalBoard)
    assert [c["title"] for c in board.call("board", {})["groups"]["take"]] == [
        "invoice model",
        "CSV parser",
    ]
    board.close()


def test_a_pulled_board_is_a_SNAPSHOT_and_it_stops_moving(
    server: BoardServer, joined: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The sentence is part of the deliverable, and so is the fact behind it.
    Nothing syncs after a pull: the host moves on, this copy does not, and
    nothing anywhere would say so — which is why the command says it itself."""
    plan(client(server, BERNA))
    assert pulled(f"{host_of(server)}/{BOARD}") == 0
    printed = capsys.readouterr().out
    assert "SNAPSHOT" in printed and "STOPS MOVING" in printed
    assert "nothing syncs" in printed
    assert "destroys nothing" in printed

    # The host moves on. The local copy does not, and never will.
    after = client(server, BERNA)
    after.call(
        "plan",
        {
            "milestone": "second chapter",
            "goal": "written after the pull",
            "tasks": [{"title": "too late", "spec": "never seen here", "files": ["z.py"]}],
        },
    )
    board = taskops.board.open_board(joined, BERNA)
    assert [m["title"] for m in board.call("board", {})["milestones"]] == ["MVP facturador"]
    board.close()
    assert len(client(server, BERNA).call("board", {})["milestones"]) == 2


def test_an_interrupted_pull_re_runs_to_a_no_op_and_finishes_the_job(
    server: BoardServer, joined: Path
) -> None:
    """Criterion 2, and the interruption is real: half the log is written and the
    process dies before step 5. The retry must NOT refuse itself — "is there a
    local board here" would, which is why step 1 asks by ID instead — and it must
    not duplicate a line either: the cache ignores a repeated id and the log
    does not, so the write is filtered against what is already held."""
    from taskops.store.stores import Stores

    plan(client(server, BERNA))
    theirs = host_log(server)
    honest = Stores.write

    def dies(self: Stores, events: Any) -> int:
        rows = list(events)
        honest(self, rows[: len(rows) // 2])
        raise RuntimeError("the laptop closed")

    # Its OWN context: `monkeypatch.undo()` would also undo the `joined`
    # fixture's chdir and env, and the retry has to run where the first one did.
    with pytest.MonkeyPatch.context() as broken:
        broken.setattr(Stores, "write", dies)
        with pytest.raises(RuntimeError):
            pulled(f"{host_of(server)}/{BOARD}")

    # Half a history on disk and a config that never flipped: still the host's.
    partial = ids_in(local_log(joined).read_text(encoding="utf-8"))
    assert 0 < len(partial) < len(ids_in(theirs))
    assert read_config(joined)["url"] == url_of(server)

    assert pulled(f"{host_of(server)}/{BOARD}") == 0
    whole = local_log(joined).read_text(encoding="utf-8")
    assert ids_in(whole) == ids_in(theirs)  # no duplicate, no reordering
    assert "url" not in read_config(joined)

    # And a THIRD run, with nothing left to do, is a pure no-op — including the
    # sign-in, which comes off the `login` block the flip deliberately kept.
    assert pulled(f"{host_of(server)}/{BOARD}") == 0
    assert local_log(joined).read_text(encoding="utf-8") == whole
    assert host_log(server) == theirs


def test_a_pull_over_a_history_the_host_does_not_hold_names_both_ways_out(
    server: BoardServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`join`'s orphan refusal, from the other side: two histories in one log is
    what would happen, and it is refused with the two commands that avoid it.
    Judged by ID and not by existence — the previous test is the reason."""
    repo = local_repo(tmp_path, "otra")
    mine = local_log(repo).read_text(encoding="utf-8")
    plan(client(server, BERNA))
    monkeypatch.setenv("TASKOPS_ACTOR", BERNA)
    monkeypatch.chdir(repo)
    token, _ = server.mounts.credentials.mint(BERNA, BOARD, _clock.now())
    (repo / ".taskops" / "remote.json").write_text(json.dumps({"token": token}), encoding="utf-8")

    with pytest.raises(TaskopsError) as refused:
        pulled(f"{host_of(server)}/{BOARD}")
    assert "does not hold" in str(refused.value)
    assert "--discard-local" in str(refused.value)
    assert "taskops board pull" in str(refused.value)

    # Nothing was written by the refusal, on either side.
    assert local_log(repo).read_text(encoding="utf-8") == mine
    assert "url" not in read_config(repo)


def test_a_pull_that_arrives_short_stops_before_the_config_flips(
    server: BoardServer, joined: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Step 4, against a pull that really is short — one event never reaches the
    store. The ID sets disagree, the command STOPS, and this checkout still
    reads the host: without the comparison it would have reported success and
    started reading a board with a hole in it."""
    from taskops.store.stores import Stores

    plan(client(server, BERNA))
    honest = Stores.write

    def short(self: Stores, events: Any) -> int:
        return honest(self, list(events)[:-1])

    monkeypatch.setattr(Stores, "write", short)
    with pytest.raises(TaskopsError) as stopped:
        pulled(f"{host_of(server)}/{BOARD}")
    assert "did not arrive whole" in str(stopped.value)
    assert "1 of the host's" in str(stopped.value)

    assert read_config(joined)["url"] == url_of(server)  # step 5 never ran


def test_a_board_that_moved_under_the_read_is_refused_and_nothing_is_written(
    server: BoardServer, joined: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The check the ID comparison cannot make: a page silently lost shrinks BOTH
    sides of it and agrees with itself. `total` is the log's own length, so a
    read that does not add up refuses before a single event is written down."""
    plan(client(server, BERNA))
    honest = RemoteBoard.call

    def inflated(self: RemoteBoard, verb: str, args: dict[str, Any]) -> dict[str, Any]:
        answer = honest(self, verb, args)
        return {**answer, "total": int(answer["total"]) + 1} if verb == "events" else answer

    monkeypatch.setattr(RemoteBoard, "call", inflated)
    with pytest.raises(TaskopsError, match="moved while it was being read"):
        pulled(f"{host_of(server)}/{BOARD}")

    assert not local_log(joined).exists()
    assert read_config(joined)["url"] == url_of(server)


def test_the_whole_log_comes_down_page_by_page_and_not_just_its_first_page(
    server: BoardServer, joined: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The paging is keyset by `seq`, so a log longer than one page must arrive
    whole and in order. The page size is shrunk rather than the history grown:
    what is being pinned is the cursor loop, not the server's constant."""
    from taskops.cli import paging

    plan(client(server, BERNA))
    theirs = host_log(server)
    assert len(ids_in(theirs)) > 3
    monkeypatch.setattr(paging, "MAX_PAGE", 2)

    assert pulled(f"{host_of(server)}/{BOARD}") == 0
    assert ids_in(local_log(joined).read_text(encoding="utf-8")) == ids_in(theirs)


def test_pulling_added_no_verb_to_either_registry(server: BoardServer, owner: str) -> None:
    """No replication channel, and this is the wall that says so: the whole
    command reads the log through `events`, the verb the dashboard's Event pane
    already uses. A `board.pull` — or any sync door — is the banned thing
    (ARCHITECTURE §11), so the host must not answer one and must not have grown
    one to make this feature possible."""
    from taskops.verbs import REGISTRY

    assert not [verb for verb in REGISTRY if "pull" in verb or "sync" in verb]
    with pytest.raises(BadRequest, match="this host's own verbs are"):
        admin(server, owner, "board.pull", {"board": BOARD})


def test_an_event_that_fails_its_own_hash_is_never_written_down(
    server: BoardServer, joined: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reader of a FILE quarantines a line whose id does not match its
    content (`store/log.py`), and the same rule has to hold on the wire: an
    event tampered with in flight would otherwise be written into a fresh log
    that looks trustworthy, in a second place, with nobody having verified it."""
    plan(client(server, BERNA))
    honest = RemoteBoard.call

    def forged(self: RemoteBoard, verb: str, args: dict[str, Any]) -> dict[str, Any]:
        answer = honest(self, verb, args)
        if verb != "events":
            return answer
        rows = [dict(row) for row in answer["events"]]
        rows[0]["actor"] = "dev:mallory"
        return {**answer, "events": rows}

    monkeypatch.setattr(RemoteBoard, "call", forged)
    with pytest.raises(TaskopsError, match="does not match its own content"):
        pulled(f"{host_of(server)}/{BOARD}")

    assert not local_log(joined).exists()
    assert read_config(joined)["url"] == url_of(server)
# ── a board comes OFF a host, and only when the history is not lost ──────────
#
# The last one-directional edge in a board's life: `board create` made one and
# `board push` filled it, and taking one away meant ssh and `rm -rf`. This is
# the door for it, and the whole of the door is the guardrail — the only
# command in taskops that destroys something nobody can regenerate.


def board_ids(httpd: BoardServer, name: str) -> list[str]:
    """The ids the HOST really holds — the left-hand side of every comparison
    below, read from the board and never from what a caller claimed."""
    return sorted(httpd.mounts.stores(name).ids())


def bare_repo(tmp_path: Path, name: str = "joined") -> Path:
    """A checkout with no local history at all — what a repo that JOINED the
    hosted board looks like: it reads the board over the wire and holds nothing."""
    repo = tmp_path / name
    (repo / ".taskops").mkdir(parents=True)
    (repo / ".taskops" / "board.json").write_text("{}\n", encoding="utf-8")
    return repo


def pulled_into(repo: Path, httpd: BoardServer, name: str) -> Path:
    """What `taskops board pull` leaves behind (tk-069df3, landing beside this):
    the host's whole log in this checkout's local board. Written directly rather
    than by calling that command, so these tests pin `board rm`'s own guardrail
    and stay green whichever of the two lands first."""
    local = repo / ".taskops" / "board"
    local.mkdir(parents=True, exist_ok=True)
    source = (httpd.mounts.root / name / "events.jsonl").read_text(encoding="utf-8")
    (local / "events.jsonl").write_text(source, encoding="utf-8")
    return local


def removed(target: str, key: Path, discard: bool = False) -> int:
    from taskops.cli import rm

    return rm.run(
        argparse.Namespace(action="rm", target=target, key=str(key), discard_history=discard)
    )


def test_board_rm_refuses_a_history_this_checkout_does_not_hold_and_names_both_ways_out(
    server: BoardServer, keyed: Path, owner: str, tmp_path: Path, monkeypatch: Any
) -> None:
    """Criterion 3, end to end over the socket. The checkout is joined, so it
    holds NONE of the ids — and the sentence a human gets names the two commands
    that make a removal possible, the way `join`'s orphan refusal does."""
    plan(client(server, BERNA))  # the board now has a history worth losing
    before = board_ids(server, BOARD)
    monkeypatch.chdir(bare_repo(tmp_path))

    with pytest.raises(TaskopsError) as refused:
        removed(f"{host_of(server)}/{BOARD}", keyed)

    said = str(refused.value)
    assert f"{len(before)} of the host's {len(before)} event(s) are not here" in said
    assert f"taskops board pull {BOARD}" in said
    assert f"taskops board rm {BOARD} --discard-history" in said
    assert "there is no --force" in said
    # Nothing happened: the board is there, event for event.
    assert (server.mounts.root / BOARD).is_dir()
    assert board_ids(server, BOARD) == before


def test_board_rm_removes_a_history_this_checkout_holds_and_says_how_big_it_was(
    server: BoardServer, keyed: Path, owner: str, tmp_path: Path, monkeypatch: Any
) -> None:
    """Criterion 4. The same checkout, after the history came down: every id the
    host reports is held here, so the removal is not a loss and goes through —
    and the answer says the SIZE of what just went, while the terminal is open."""
    plan(client(server, BERNA))
    theirs = board_ids(server, BOARD)
    repo = bare_repo(tmp_path)
    local = pulled_into(repo, server, BOARD)
    monkeypatch.chdir(repo)

    assert removed(f"{host_of(server)}/{BOARD}", keyed) == 0

    assert not (server.mounts.root / BOARD).exists()
    assert [row["name"] for row in admin(server, owner, "board.list", {})["boards"]] == []
    # The local copy is untouched by the removal and is now THE copy — every id
    # the host reported a moment ago is still readable here, from the log itself.
    from taskops.cli import rm

    assert (local / "events.jsonl").exists()
    assert sorted(rm.held(repo)) == theirs


def test_the_answer_carries_what_was_removed_and_how_many_events_went_with_it(
    server: BoardServer, owner: str
) -> None:
    """A removal writes to no log — the board is the log, and it is gone. So the
    ANSWER is the only record there will ever be, and it counts the events the
    board really held, read from it before the directory went."""
    plan(client(server, BERNA))
    theirs = board_ids(server, BOARD)

    answer = admin(server, owner, "board.remove", {"board": BOARD, "held": theirs})

    assert answer["board"] == BOARD and answer["removed"] is True
    assert answer["events"] == len(theirs)
    assert answer["held_elsewhere"] is True
    assert answer["gap"] == f"all {len(theirs)} event(s) are held here"


def test_discard_history_destroys_it_anyway_and_the_answer_names_what_was_lost(
    server: BoardServer, owner: str
) -> None:
    """The way out the refusal offers, and it is not a silent one: the board goes
    even though nothing else held it, and the answer says exactly that so the
    sentence somebody typed on purpose is also the sentence they can quote."""
    plan(client(server, BERNA))
    theirs = board_ids(server, BOARD)

    answer = admin(server, owner, "board.remove", {"board": BOARD, "discard_history": True})

    assert answer["events"] == len(theirs) and answer["held_elsewhere"] is False
    assert f"{len(theirs)} of the host's {len(theirs)} event(s) are not here" in answer["gap"]
    assert not (server.mounts.root / BOARD).exists()


def test_the_flag_is_named_for_what_it_destroys_and_a_force_is_not_a_synonym(
    server: BoardServer, owner: str
) -> None:
    """ARCHITECTURE.md §11: no `--force`, and not as an alias either. A caller
    reaching for the word it knows from every other tool is refused, and so is a
    truthy string — only a literal `true` destroys a history, because "yes" is
    what a shell hands over when a variable was never set."""
    plan(client(server, BERNA))
    for args in ({"force": True}, {"discard_history": "yes"}, {"discard_history": 1}):
        with pytest.raises(Refused, match="would destroy a history"):
            admin(server, owner, "board.remove", {"board": BOARD, **args})
    assert (server.mounts.root / BOARD).is_dir()


def test_a_removed_name_is_created_EMPTY_and_the_two_histories_wall_still_stands(
    server: BoardServer, keyed: Path, owner: str, tmp_path: Path, monkeypatch: Any
) -> None:
    """Criterion 5, and the reason `Mounts.forget` exists. A process keeps a
    `Stores` per board for its own lifetime and sqlite goes on answering through
    an unlinked file — so without dropping the handle, `board create` on the name
    just removed would hand the destroyed history straight back, and a push into
    the "new" board would be refused as two histories. Removal is not a way to
    smuggle a second history into one name, in either direction."""
    plan(client(server, BERNA))
    admin(server, owner, "board.remove", {"board": BOARD, "discard_history": True})

    made = admin(server, owner, "board.create", {"name": BOARD})
    assert made["seq"] == 1  # the birth certificate, and nothing else
    assert len(server.mounts.stores(BOARD).ids()) == 1

    repo = local_repo(tmp_path)
    mine = local_log(repo).read_text(encoding="utf-8").strip().splitlines()
    monkeypatch.chdir(repo)
    assert pushed(f"{host_of(server)}/{BOARD}", keyed) == 0  # genuinely empty
    assert server.mounts.stores(BOARD).head() == len(mine) + 1

    # And the wall is up on the fresh board, exactly as it is on any other.
    stranger = local_repo(tmp_path, "stranger")
    theirs = local_log(stranger).read_text(encoding="utf-8").strip().splitlines()
    with pytest.raises(Refused) as second:
        admin(server, owner, "board.ingest", {"board": BOARD, "events": theirs})
    assert "this push never observed" in str(second.value)


def test_a_removed_board_stops_being_served_by_the_process_that_held_it_open(
    server: BoardServer, owner: str
) -> None:
    """The other half of `forget`, from the reader's side: a board removed under
    a live server is gone for that server too, immediately, without a restart."""
    plan(client(server, BERNA))
    admin(server, owner, "board.remove", {"board": BOARD, "discard_history": True})

    with pytest.raises(NotFound, match="no board named"):
        client(server, BERNA).call("board", {})


def test_a_removal_records_nothing_in_any_other_boards_log(
    server: BoardServer, owner: str
) -> None:
    """There is no log left to record it in, and the nearest one is not a
    substitute: a board holding another board's history is exactly the confusion
    the whole storage model exists to avoid."""
    admin(server, owner, "board.create", {"name": "otro"})
    untouched = (server.mounts.root / "otro" / "events.jsonl").read_text(encoding="utf-8")
    plan(client(server, BERNA))

    admin(server, owner, "board.remove", {"board": BOARD, "discard_history": True})

    assert not (server.mounts.root / BOARD).exists()
    assert (server.mounts.root / "otro" / "events.jsonl").read_text(encoding="utf-8") == untouched


def test_removing_a_board_is_the_server_owners_move_and_a_member_is_refused(
    server: BoardServer, owner: str, tmp_path: Path
) -> None:
    """Server scope, OWNER only — the same table and the same gate as
    `board.visibility`, so there is no second door onto destroying a board."""
    hers, _ = member(server, tmp_path)
    with pytest.raises(Refused) as refused:
        admin(server, hers, "board.remove", {"board": BOARD, "discard_history": True})
    assert "member may not board.remove" in str(refused.value)
    assert "server OWNER's move" in str(refused.value)
    assert (server.mounts.root / BOARD).is_dir()


def test_a_name_that_is_not_a_board_removes_nothing_and_a_bad_name_never_reaches_disk(
    server: BoardServer, owner: str
) -> None:
    """`board rm` is not `rm`: the name is checked against the same wall every
    other door uses (`http/mounts.py::named`) BEFORE it is joined to a path, and
    an unknown board is a refusal rather than a successful no-op."""
    before = sorted(p.name for p in server.mounts.root.iterdir())
    with pytest.raises(NotFound) as missing:
        admin(server, owner, "board.remove", {"board": "fantasma", "discard_history": True})
    assert "no board named 'fantasma'" in str(missing.value)
    assert "taskops board ls" in str(missing.value)

    for escape in ("../../etc", "/etc", "Facturador"):
        with pytest.raises(BadRequest, match="names are"):
            admin(server, owner, "board.remove", {"board": escape, "discard_history": True})
    assert sorted(p.name for p in server.mounts.root.iterdir()) == before


def test_the_cli_routes_board_rm_and_knows_no_force_flag(monkeypatch: Any) -> None:
    """The wiring, pinned where a Namespace built by hand cannot see it: `board
    rm` is a real action with a real `--discard-history`, and `--force` is not a
    spelling argparse accepts — the flag has to name what it destroys."""
    from taskops.cli import rm
    from taskops.cli.main import main as cli

    seen: list[argparse.Namespace] = []
    monkeypatch.setattr(rm, "run", lambda args: (seen.append(args), 0)[1])
    assert cli(["board", "rm", "facturador", "--discard-history"]) == 0
    assert seen[0].action == "rm" and seen[0].target == "facturador"
    assert seen[0].discard_history is True

    assert cli(["board", "rm", "facturador"]) == 0
    assert seen[1].discard_history is False

    with pytest.raises(SystemExit):
        cli(["board", "rm", "facturador", "--force"])
def test_a_client_that_hangs_up_is_not_printed_as_a_crash(
    server: BoardServer, capsys: pytest.CaptureFixture[str]
) -> None:
    """A browser opens several keep-alive connections per origin and closes the
    spares once the page settles; a WebSocket upgrade replaces one outright.
    socketserver answers every exception in its thread with a full traceback, so
    a healthy `taskops ui` printed thirty lines of Python internals per
    disconnect — which is how a REAL fault stops being visible.

    Everything that is not a departure still prints: the second half asserts
    that, because a handler that swallows errors is the worse bug."""
    capsys.readouterr()
    try:
        raise ConnectionResetError(54, "Connection reset by peer")
    except ConnectionResetError:
        server.handle_error(None, ("127.0.0.1", 1))
    assert capsys.readouterr().err == ""

    try:
        raise ValueError("a real fault, and it must be seen")
    except ValueError:
        server.handle_error(None, ("127.0.0.1", 1))
    assert "a real fault" in capsys.readouterr().err


# ── `taskops board forge` SYNCS the team: collaborators → .keys → enroll ─────
#
# Appended as ONE contiguous tail block, for the reason the block above says: parallel worktrees merge two tails cleanly and interleaved edits
# not at all. The stub is a REAL socket serving BOTH GitHub endpoints this side
# calls — `api.github.com/repos/…/collaborators` (paginated, authenticated) and
# `github.com/<login>.keys` (plain text, PUBLIC) — because the point of the
# chapter is exactly which of the two carries the token, and monkeypatching
# `_wire` away would test neither the header nor the pagination.


class Hub:
    """The stub's answers, and what it SAW. The second half is the test."""

    def __init__(self) -> None:
        self.people: list[dict[str, Any]] = []
        self.published: dict[str, str] = {}
        self.status = 200
        self.seen: list[tuple[str, str]] = []  # (path, Authorization)


@pytest.fixture()
def hub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Hub]:
    from http.server import HTTPServer, BaseHTTPRequestHandler

    from taskops.cli import github as asking

    stub = Hub()

    class Stub(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's contract
            stub.seen.append((self.path, self.headers.get("Authorization", "")))
            if self.path.endswith(".keys"):
                who = self.path.rsplit("/", 1)[1][: -len(".keys")]
                return self._say(200, stub.published.get(who, ""), "text/plain")
            page = int(dict(_query(self.path)).get("page", "1"))
            size = asking.PAGE
            rows = stub.people[(page - 1) * size : page * size]
            self._say(stub.status, json.dumps(rows), "application/json")

        def _say(self, status: int, text: str, kind: str) -> None:
            body = text.encode()
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: Any) -> None:
            return

    httpd = HTTPServer(("127.0.0.1", 0), Stub)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{httpd.server_address[1]}"
    monkeypatch.setattr(asking, "API", root)
    monkeypatch.setattr(asking, "KEYS", root)
    # `gh auth token` is the FIRST source, so a real `gh` on the runner's PATH
    # would hand a real token to this socket. A fake one on PATH answers first.
    fake_gh(tmp_path / "ghbin", prints=TOKEN)
    on_path(monkeypatch, tmp_path / "ghbin")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    yield stub
    httpd.shutdown()
    httpd.server_close()


def _query(path: str) -> list[tuple[str, str]]:
    _, _, tail = path.partition("?")
    return [(bit.split("=")[0], bit.split("=")[1]) for bit in tail.split("&") if "=" in bit]


def collaborator(login: str, need: str = "push", kind: str = "User") -> dict[str, Any]:
    return {"login": login, "type": kind, "permissions": {"pull": True, need: True}}


def forge_sync(server: BoardServer, keyed: Path, repo: str = "bernatch22/taskops") -> int:
    from taskops.cli import main

    return main(["board", "forge", f"{host_of(server)}/{BOARD}", repo, "--key", str(keyed)])


def test_the_forge_enrols_every_collaborator_with_push_across_every_page(
    server: BoardServer, keyed: Path, virgin: Path, hub: Hub, tmp_path: Path,
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Criterion 1. Five collaborators over THREE pages — the loop is the test:
    stopping at the first page would enrol two of them and report the other
    three as drift, which reads to the owner as a revocation list.

    `Bot` and a `pull`-only account are in the list on purpose: the door in
    `http/github.py` grants on `permissions[need]`, so the sync that fills the
    host has to read the same field or the two disagree about who works here."""
    from taskops.cli import github as asking

    monkeypatch.setattr(asking, "PAGE", 2)  # 5 people, pages of 2: 2 + 2 + 1
    keys = {name: keygen(tmp_path / f"{name}_key") for name in ("ana", "leo", "dan", "mia")}
    hub.published = {name: pubkey(key) for name, key in keys.items()}
    hub.people = [
        collaborator("Ana"), collaborator("leo"), collaborator("dan"),
        collaborator("robot", kind="Bot"), collaborator("mia"),
    ]

    assert forge_sync(server, keyed) == 0
    printed = capsys.readouterr().out
    assert "4 collaborator(s) with push on bernatch22/taskops" in printed  # the Bot is not one
    assert "enrolled  ana, dan, leo, mia" in printed

    # Three pages were really asked for, and the third ended the loop by being short.
    pages = [path for path, _ in hub.seen if "/collaborators" in path]
    assert [path.rsplit("page=", 1)[1] for path in pages] == ["1", "2", "3"]

    # `Ana` with a capital is `ana` on this host: a principal name is [a-z0-9._-],
    # and a login GitHub happily capitalises would otherwise be refused mid-batch.
    store = server.mounts.host.store()
    assert sorted(p.name for p in store.principals()) == ["ana", "berna", "dan", "leo", "mia"]
    assert sign_in(server, "ana", keys["ana"])["role"] == "member"  # the key really signs

    # Re-running it re-syncs and writes nothing: idempotent all the way down.
    written = signers_of(server)
    assert forge_sync(server, keyed) == 0
    assert "unchanged ana, dan, leo, mia" in capsys.readouterr().out
    assert signers_of(server) == written


def test_a_collaborator_with_no_key_on_github_is_NAMED_with_their_way_in(
    server: BoardServer, keyed: Path, virgin: Path, hub: Hub, tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Criterion 2. There is nothing to enrol for somebody who pushes over
    HTTPS, and the failure mode this pins is the SILENT one: a team of three
    reported as two is a bug found three weeks later by the person left out."""
    hub.published = {"ana": pubkey(keygen(tmp_path / "ana_key"))}
    hub.people = [collaborator("ana"), collaborator("dan"), collaborator("mia")]

    assert forge_sync(server, keyed) == 0
    printed = capsys.readouterr().out
    assert "no ssh key published on GitHub — 2, not enrolled" in printed
    assert "taskops invite dan" in printed and "taskops invite mia" in printed
    assert "github.com/dan.keys is empty" in printed
    assert server.mounts.host.store().principal("dan") is None


def test_the_drift_is_REPORTED_with_the_revoke_command_and_nothing_revokes_itself(
    server: BoardServer, keyed: Path, virgin: Path, hub: Hub, tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Criterion 3, and the milestone's own decision: a sync ADDS. `ana` came in
    through an invite and is not a GitHub login at all, so a pruning sync would
    revoke her for having been introduced the other way — she is reported, with
    the exact command, and still signs in afterwards. The OWNER is never in that
    list: a `revoke` line beside the account running this is a way to lock
    yourself out of your own host."""
    _, hers = member(server, tmp_path)
    leo = keygen(tmp_path / "leo_key")
    hub.published = {"leo": pubkey(leo)}
    hub.people = [collaborator("leo")]

    assert forge_sync(server, keyed) == 0
    printed = capsys.readouterr().out
    named = server.mounts.host.store().keys("ana")[0].fingerprint
    assert "on this host but NOT a collaborator any more — 1, nothing revoked" in printed
    assert f"ana                      taskops revoke --key {named}" in printed
    assert "berna" not in printed.split("nothing revoked")[1]  # the owner is not drift
    assert "introduced by invite belongs here legitimately" in printed

    assert sign_in(server, "ana", hers)["role"] == "member"  # nothing was revoked
    assert sign_in(server, "berna", keyed)["role"] == "owner"


def test_the_owners_token_is_spent_on_ONE_endpoint_and_written_nowhere(
    server: BoardServer, keyed: Path, virgin: Path, hub: Hub, tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Criterion 4. The token authenticates the COLLABORATOR pages and nothing
    else — `<login>.keys` is public, and sending a credential to it would spend
    the owner's identity on a request that does not need one. Then the grep: the
    host's whole tree and the checkout's, not the two files somebody remembered.
    """
    hub.published = {"leo": pubkey(keygen(tmp_path / "leo_key"))}
    hub.people = [collaborator("leo")]
    assert forge_sync(server, keyed) == 0

    carried = {path.split("?")[0]: auth for path, auth in hub.seen}
    assert carried["/repos/bernatch22/taskops/collaborators"] == f"Bearer {TOKEN}"
    assert carried["/leo.keys"] == ""  # public: no credential is spent on it

    needle = TOKEN.encode()
    files = [p for p in server.mounts.root.rglob("*") if p.is_file()]
    files += [p for p in virgin.rglob("*") if p.is_file()]
    assert any(b"ssh-ed25519" in p.read_bytes() for p in files)  # the scan reads real bytes
    for path in files:
        assert needle not in path.read_bytes(), f"the GitHub token reached {path}"
    assert TOKEN not in capsys.readouterr().out


def test_github_refusing_the_owners_token_names_the_repo_and_enrols_nobody(
    server: BoardServer, keyed: Path, virgin: Path, hub: Hub,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A 401/403/404 is a status, not something a person can act on — and the
    token is in none of the three sentences. The declaration is already recorded
    when this happens, which is what makes the fix "run the same command again"."""
    hub.people = [collaborator("leo")]
    for status, said in ((401, "rejected that token"), (403, "SSO"), (404, "no repository")):
        hub.status = status
        assert forge_sync(server, keyed) == 1
        printed = capsys.readouterr()
        assert said in printed.err and TOKEN not in printed.err
        assert "bernatch22/taskops" in printed.err
    assert [p.name for p in server.mounts.host.store().principals()] == ["berna"]


def test_the_dev_whose_key_the_sync_published_joins_with_two_words(
    server: BoardServer, keyed: Path, virgin: Path, hub: Hub, project: Path, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The chapter's whole point, end to end and from BOTH sides.

    The owner syncs; then a dev in a fresh clone — one that has joined nothing,
    holds no invite and carries no token — types `taskops join` and is in. Her
    key was published on GitHub before any of this and enrolled without her, so
    there is nothing left for her side to prove: the bare branch of
    `cli/commands.py::join` signs in with the key it discovers and writes a
    session. This replaces the six tests that pinned the door she used to have
    to knock on, and it is stricter than they were — GitHub is asked NOTHING on
    her side, `gh` on her PATH or not.
    """
    from taskops.cli import commands

    hers = keygen(tmp_path / "ana_key")
    hub.published = {"ana": pubkey(hers)}
    hub.people = [collaborator("ana")]
    assert forge_sync(server, keyed) == 0
    asked = len(hub.seen)

    # Her clone: `.taskops/board.json` travels with it and carries the address,
    # which is the whole of `taskops join` — no URL, no --key, no --invite.
    from taskops import identity

    carried = project / ".taskops"
    carried.mkdir(parents=True, exist_ok=True)
    (carried / "board.json").write_text(json.dumps({"url": url_of(server)}), encoding="utf-8")
    monkeypatch.chdir(project)
    monkeypatch.setattr(identity, "discover_key", lambda: hers)
    assert commands.join(project, "", ANA) == 0

    config = json.loads((project / ".taskops" / "remote.json").read_text(encoding="utf-8"))
    assert config["token"] and config["token_expires"] > _clock.now()
    assert config["login"] == {"host": host_of(server), "principal": "ana", "key": str(hers)}
    assert RemoteBoard(url_of(server), config["token"], ANA).call("board", {})["seq"] >= 0
    assert server.mounts.host.store().role_of("ana") == "member"

    assert len(hub.seen) == asked  # her side asked GitHub nothing at all
    for path in (p for p in project.rglob("*") if p.is_file()):
        assert TOKEN.encode() not in path.read_bytes(), f"the GitHub token reached {path}"


# ── the git doors: clone, fetch and PUSH against the board's OWN repo.git ────
#
# §16, "The host becomes the remote": /<board>/repo.git speaks smart-HTTP over
# the same door as everything else, the token riding in HTTP Basic's password
# field. These tests run the REAL git client against the live server — the
# protocol is git's own, so the proof has to be too.


def sh_git(*args: str, cwd: Path) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(  # noqa: S603
        # credential.helper= (empty) RESETS the helper list: without it the
        # machine's osxkeychain quietly saves the pushed token and hands it to
        # the "anonymous" clone, and the visibility tests test the keychain.
        ["git", "-c", "credential.helper=", "-c", "user.email=t@test", "-c", "user.name=t", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        check=False,
    )


def seeded(tmp_path: Path) -> Path:
    src = tmp_path / "seed"
    src.mkdir()
    assert sh_git("init", "-b", "master", ".", cwd=src).returncode == 0
    (src / "hello.txt").write_text("v1\n", encoding="utf-8")
    assert sh_git("add", ".", cwd=src).returncode == 0
    assert sh_git("commit", "-m", "first", cwd=src).returncode == 0
    return src


def remote_of(httpd: BoardServer, token: str = "", board: str = BOARD) -> str:
    """The address `taskops remote` would spell — token in Basic's password."""
    cred = f"x:{token}@" if token else ""
    return f"http://{cred}127.0.0.1:{httpd.server_address[1]}/{board}/repo.git"


def hosted(httpd: BoardServer, board: str = BOARD) -> Path:
    return httpd.mounts.root / board / "repo.git"


def host_ref(httpd: BoardServer, ref: str) -> str:
    done = sh_git("rev-parse", "--verify", "--quiet", ref, cwd=hosted(httpd))
    return done.stdout.strip()


def writer(httpd: BoardServer, subject: str = BERNA) -> str:
    token, _ = httpd.mounts.credentials.mint(subject, BOARD, _clock.now())
    return token


def test_push_clone_and_fetch_round_trip_on_the_boards_own_repo(
    server: BoardServer, tmp_path: Path
) -> None:
    """Criterion 1 whole: the first push CREATES repo.git (never a read — see
    gitwork/bare.py), a clone gets the work back, a fetch sees the next push.
    An agent: credential pushes too — workers are who bind.py pushes as."""
    seed = seeded(tmp_path)
    token = writer(server)
    pushed = sh_git("push", remote_of(server, token), "master", cwd=seed)
    assert pushed.returncode == 0, pushed.stderr

    repo = hosted(server)
    assert (repo / "HEAD").is_file()  # created by the push, beside events.jsonl
    for knob in ("receive.denyDeletes", "receive.denyNonFastForwards"):
        assert sh_git("config", knob, cwd=repo).stdout.strip() == "true"

    copy = tmp_path / "copy"
    cloned = sh_git("clone", remote_of(server, token), str(copy), cwd=tmp_path)
    assert cloned.returncode == 0, cloned.stderr
    assert (copy / "hello.txt").read_text(encoding="utf-8") == "v1\n"

    (seed / "hello.txt").write_text("v2\n", encoding="utf-8")
    assert sh_git("commit", "-am", "second", cwd=seed).returncode == 0
    agent = writer(server, W1)
    assert sh_git("push", remote_of(server, agent), "master:tk-test", cwd=seed).returncode == 0
    fetched = sh_git("fetch", "origin", cwd=copy)
    assert fetched.returncode == 0, fetched.stderr
    tip = sh_git("rev-parse", "HEAD", cwd=seed).stdout.strip()
    assert sh_git("rev-parse", "origin/tk-test", cwd=copy).stdout.strip() == tip


def test_a_public_board_is_clonable_anonymously_and_a_private_one_refuses(
    server: BoardServer, tmp_path: Path, owner: str
) -> None:
    """READ follows visibility exactly as /rpc does. Private first, so the same
    board proves both walls; the anonymous clone runs no verb and leaves no
    presence row, exactly as the crawl test pins for the JSON doors."""
    seed = seeded(tmp_path)
    assert sh_git("push", remote_of(server, writer(server)), "master", cwd=seed).returncode == 0

    refused = sh_git("clone", remote_of(server), str(tmp_path / "no"), cwd=tmp_path)
    assert refused.returncode != 0
    assert not (tmp_path / "no" / "hello.txt").exists()

    publish(server, owner)
    cloned = sh_git("clone", remote_of(server), str(tmp_path / "yes"), cwd=tmp_path)
    assert cloned.returncode == 0, cloned.stderr
    assert (tmp_path / "yes" / "hello.txt").read_text(encoding="utf-8") == "v1\n"
    assert "anon" not in dict(_presence(server))


def test_an_anonymous_push_is_refused_and_creates_no_repo(
    server: BoardServer, tmp_path: Path, owner: str
) -> None:
    """A push is a write under §11's ban, PUBLIC board included — and since the
    repo is created by the first push, a refused stranger creates nothing."""
    publish(server, owner)
    seed = seeded(tmp_path)
    pushed = sh_git("push", remote_of(server), "master", cwd=seed)
    assert pushed.returncode != 0
    assert not hosted(server).exists()


def test_a_read_only_credential_clones_but_may_not_push(
    server: BoardServer, tmp_path: Path
) -> None:
    """The auth split, one credential on both sides of it: caps decide, and the
    refusal is the standing one — no second rule invented for git."""
    seed = seeded(tmp_path)
    assert sh_git("push", remote_of(server, writer(server)), "master", cwd=seed).returncode == 0
    reader, _ = server.mounts.credentials.mint(ANA, BOARD, _clock.now(), caps="read")

    cloned = sh_git("clone", remote_of(server, reader), str(tmp_path / "ro"), cwd=tmp_path)
    assert cloned.returncode == 0, cloned.stderr

    before = host_ref(server, "master")
    (seed / "hello.txt").write_text("v2\n", encoding="utf-8")
    assert sh_git("commit", "-am", "second", cwd=seed).returncode == 0
    pushed = sh_git("push", remote_of(server, reader), "master", cwd=seed)
    assert pushed.returncode != 0
    assert host_ref(server, "master") == before


def test_a_pushed_branch_is_readable_through_the_json_diff_door(
    server: BoardServer, tmp_path: Path
) -> None:
    """The acceptance the reversal exists for: the window's diff is read from
    the board's OWN repository, no forge declared, no mirror consulted."""
    seed = seeded(tmp_path)
    (seed / "hello.txt").write_text("v2\n", encoding="utf-8")
    assert sh_git("commit", "-am", "second", cwd=seed).returncode == 0
    token = writer(server)
    assert sh_git("push", remote_of(server, token), "master:tk-seen", cwd=seed).returncode == 0

    with urlopen(f"{url_of(server)}/git/commit/tk-seen?token={token}", timeout=5) as answer:
        body = json.loads(answer.read())
    assert body["ok"] and "hello.txt" in body["data"]["patch"]


def test_the_host_refuses_a_ref_deletion(server: BoardServer, tmp_path: Path) -> None:
    """The host NEVER prunes — enforced in the created repo's own config, so
    the very receive-pack that would move the ref is the process refusing."""
    seed = seeded(tmp_path)
    token = writer(server)
    assert sh_git("push", remote_of(server, token), "master:tk-kept", cwd=seed).returncode == 0

    gone = sh_git("push", remote_of(server, token), "--delete", "tk-kept", cwd=seed)
    assert gone.returncode != 0
    assert "deny deleting" in (gone.stderr + gone.stdout) or host_ref(server, "tk-kept")
    assert host_ref(server, "tk-kept")


def test_the_host_refuses_a_non_fast_forward_even_forced(
    server: BoardServer, tmp_path: Path
) -> None:
    """A force is a client-side word; the refusal is the server process's own
    config, so `--force` changes nothing and the landed history survives."""
    seed = seeded(tmp_path)
    (seed / "hello.txt").write_text("v2\n", encoding="utf-8")
    assert sh_git("commit", "-am", "second", cwd=seed).returncode == 0
    token = writer(server)
    assert sh_git("push", remote_of(server, token), "master", cwd=seed).returncode == 0
    before = host_ref(server, "master")

    assert sh_git("reset", "--hard", "HEAD~1", cwd=seed).returncode == 0
    (seed / "hello.txt").write_text("rewritten\n", encoding="utf-8")
    assert sh_git("commit", "-am", "amended history", cwd=seed).returncode == 0
    for way in ((), ("--force",)):
        pushed = sh_git("push", *way, remote_of(server, token), "master", cwd=seed)
        assert pushed.returncode != 0, way
        assert host_ref(server, "master") == before
