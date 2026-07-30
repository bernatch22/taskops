"""Two machines, one server, one card — the collision this feature exists to prevent.

Everything here runs against the REAL server (`build_server`) rather than the contract fake in
`fakeserver.py`, and the difference is the point. The fake is right for replication, where the
question is "does the client obey a frozen contract". Here the question is "do two claims land
in ONE sqlite and does that sqlite pick a winner", and a fake cannot answer it: it would be
answering with its own invented rule instead of with the engine's primary key.

`test_two_machines_racing_for_one_card_leave_exactly_one_winner` is the card. The rest are the
ways this could be true and still be broken: a winner whose own board does not know it won, a
network failure that quietly claims locally instead, and a server that routes to itself.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator

import pytest

from taskops._errors import Unreachable
from taskops.storage import Store
from taskops.transports.http import Policy, bound_port, build_server
from taskops.usecases import add_remote, ask, init, next_task, plan, update

TOKEN = "s3cr3t-token"


class Serving:
    """A real taskops server over a real project, on an OS-chosen port."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.server = build_server("127.0.0.1", 0, root, Policy(token=TOKEN))
        self.url = f"http://127.0.0.1:{bound_port(self.server)}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def hub(tmp_path: Path) -> Iterator[Serving]:
    """The shared board: one card, ready, and nobody on it."""
    root = tmp_path / "hub"
    init(root, install_git_hooks=False)
    plan(root, [{"title": "the one card"}], actor="dev:berna")
    running = Serving(root)
    try:
        yield running
    finally:
        running.close()


def machine(where: Path, url: str) -> Path:
    """A developer's checkout that writes through `url`."""
    init(where, install_git_hooks=False)
    add_remote(where, url, TOKEN)
    return where


def the_card(root: Path) -> str:
    with Store(root) as store:
        return store.tasks.all()[0]["id"]


def holder(root: Path, card: str) -> str:
    """Who this board thinks is on the card. The LEASE, not the assignee: a claim takes a
    lease, and `assignee` is what a planner wrote down beforehand."""
    view = ask(root, card)
    return view["lease"]["actor"] if view["lease"] else ""


# ── the claim happens THERE, and comes back here ────────────────────────────────────────

def test_a_remote_claim_is_decided_in_the_servers_store(tmp_path: Path,
                                                        hub: Serving) -> None:
    """The lease has to exist on the SERVER. A claim that only ever existed in the caller's
    sqlite is the pre-feature behaviour wearing an HTTP request as a costume."""
    mine = machine(tmp_path / "mine", hub.url)
    answer = next_task(mine, actor="agent:berna/one")
    assert answer["claim"] is not None
    card = the_card(hub.root)
    assert ask(hub.root, card)["task"]["status"] == "claimed"
    assert holder(hub.root, card) == "agent:berna/one"


def test_the_winners_own_board_knows_it_won(tmp_path: Path, hub: Serving) -> None:
    """The mandatory pull, pinned. Without it the agent holds a lease the server can see and
    its own board cannot — and the commit guard, `brief` and every render read the LOCAL
    board, so the whole flow would deny the claim it just made."""
    mine = machine(tmp_path / "mine", hub.url)
    next_task(mine, actor="agent:berna/one")
    card = the_card(hub.root)
    assert ask(mine, card)["task"]["status"] == "claimed"
    assert holder(mine, card) == "agent:berna/one"


def test_two_machines_racing_for_one_card_leave_exactly_one_winner(tmp_path: Path,
                                                                   hub: Serving) -> None:
    """THE test. Two projects on two paths — two sqlite files, as two laptops would be — ask
    for the same card at the same moment through the same server.

    Before this feature both would have won, each in its own database, and the two agents
    would have found out by editing the same files. One winner and one ordinary `reason` is
    the entire deliverable.
    """
    one, two = machine(tmp_path / "one", hub.url), machine(tmp_path / "two", hub.url)
    card = the_card(hub.root)
    answers: dict[str, Any] = {}
    ready = threading.Barrier(2)

    def race(root: Path, actor: str) -> None:
        ready.wait(timeout=10)
        answers[actor] = next_task(root, actor=actor, task=card)

    racers = [threading.Thread(target=race, args=(one, "agent:berna/one")),
              threading.Thread(target=race, args=(two, "agent:ana/two"))]
    for racer in racers:
        racer.start()
    for racer in racers:
        racer.join(timeout=30)

    assert len(answers) == 2, "a racer never answered"
    winners = [who for who, answer in answers.items() if answer["claim"] is not None]
    assert len(winners) == 1, f"{len(winners)} agents hold one card: {answers}"
    losers = [answer for answer in answers.values() if answer["claim"] is None]
    assert losers[0]["reason"], "the loser was told nothing"
    assert holder(hub.root, card) == winners[0]


# ── the server's rules are the ones that apply ──────────────────────────────────────────

def test_the_servers_guard_reaches_the_client_verbatim(tmp_path: Path, hub: Serving) -> None:
    """`done` with no commit bound is refused THERE, and the sentence that says how to fix it
    is the sentence the agent reads here. Translating it into "HTTP 400" on the way back would
    throw away the only text it can act on."""
    mine = machine(tmp_path / "mine", hub.url)
    card = the_card(hub.root)
    next_task(mine, actor="agent:berna/one", task=card)
    with pytest.raises(Exception, match="no commit bound to it"):
        update(mine, card, actor="agent:berna/one", status="done", comment="finished")


def test_a_remote_update_lands_and_is_mirrored(tmp_path: Path, hub: Serving) -> None:
    mine = machine(tmp_path / "mine", hub.url)
    card = the_card(hub.root)
    next_task(mine, actor="agent:berna/one", task=card)
    update(mine, card, actor="agent:berna/one", status="review", comment="on it")
    assert ask(hub.root, card)["task"]["status"] == "review"
    assert ask(mine, card)["task"]["status"] == "review"


def test_a_malformed_actor_is_refused_rather_than_given_an_identity(tmp_path: Path,
                                                                    hub: Serving) -> None:
    """The token lets a caller name any actor; it does not let it name a nonsense one. An id
    that parses into nothing addresses no inbox and files work under a ghost."""
    mine = machine(tmp_path / "mine", hub.url)
    with pytest.raises(Exception, match="not an actor id"):
        next_task(mine, actor="berna the agent")


# ── the two silences that would make all of the above worthless ─────────────────────────

def test_offline_never_falls_back_to_a_local_claim(tmp_path: Path, hub: Serving) -> None:
    """The failure mode this card kills, in its subtlest form: a server that is down, and a
    client "helpfully" claiming in its own store. That claim is exactly the collision — so it
    raises, names the URL, and leaves the local board untouched."""
    mine = machine(tmp_path / "mine", hub.url)
    next_task(mine, actor="agent:berna/one")            # a pull, so the card is local too
    update(mine, the_card(hub.root), actor="agent:berna/one", status="released")
    hub.close()
    with pytest.raises(Unreachable, match="will NOT claim locally"):
        next_task(mine, actor="agent:berna/two")
    assert ask(mine, the_card(hub.root))["task"]["status"] == "ready"


def test_the_server_does_not_route_to_itself(tmp_path: Path, hub: Serving) -> None:
    """A `remote.json` in the store a server serves must change nothing about how it answers.
    Without the `local=True` the endpoints pass, the server would POST its own claim to the
    address in that file — to itself, forever, or in this case to a port with nothing on it.
    """
    add_remote(hub.root, "http://127.0.0.1:1", TOKEN)
    mine = machine(tmp_path / "mine", hub.url)
    assert next_task(mine, actor="agent:berna/one")["claim"] is not None


# ── a pull that fails must fail the whole call ──────────────────────────────────────────

class Halfway(BaseHTTPRequestHandler):
    """A server that grants the claim and then refuses to be read from.

    It exists to produce the one state no assertion above can reach: the write landed
    remotely and the local board cannot be brought level with it. Answering "claimed" there
    would hand the agent a lease its own tooling then denies.
    """

    def log_message(self, fmt: str, *args: Any) -> None:
        """Silence — the assertion is the output."""

    def do_POST(self) -> None:                                   # noqa: N802
        self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))
        self._json(200, {"claim": {"granted": True}, "reason": "",
                         "ready": 0, "working": 1, "blocked": 0})

    def do_GET(self) -> None:                                    # noqa: N802
        self._json(500, {"error": "this log is unreadable today"})

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def test_a_claim_the_local_board_cannot_be_told_about_fails(tmp_path: Path) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Halfway)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        mine = machine(tmp_path / "mine", f"http://127.0.0.1:{server.server_address[1]}")
        with pytest.raises(Exception, match="unreadable today"):
            next_task(mine, actor="agent:berna/one")
    finally:
        server.shutdown()
        server.server_close()
