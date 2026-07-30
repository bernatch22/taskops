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
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator

import pytest

from taskops._errors import Unreachable
from taskops.storage import Store
from taskops.transports.http import Policy, bound_port, build_server
from taskops.usecases import (
    add_remote,
    ask,
    attention,
    board,
    init,
    next_task,
    plan,
    pull,
    sync,
    update,
)

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


def test_evidence_survives_the_wire(tmp_path: Path, hub: Serving) -> None:
    """The second time this pair has been dropped by a transport, after the MCP tool — and the
    effect is worse here. For a project with a remote EVERY write routes through this endpoint,
    so a card carrying acceptance criteria could not be closed by anybody, agent or human: the
    server refused with "nothing says they were met" while the caller was staring at the
    evidence they had just typed. Found by running two clones against a real server.
    """
    card = plan(hub.root, [{"title": "with criteria", "spec": "s",
                            "acceptance": ["WHEN x THE SYSTEM SHALL y"]}],
                actor="dev:berna")["created"][0]["id"]
    mine = machine(tmp_path / "mine", hub.url)
    next_task(mine, actor="agent:berna/one", task=card)
    update(mine, card, actor="agent:berna/one", status="review", comment="handed over")

    update(mine, card, actor="dev:ana", status="done", no_code=True,
           comment="checked", evidence="WHEN x THE SYSTEM SHALL y: ran it, it holds")

    assert ask(hub.root, card)["task"]["status"] == "done"


def test_a_reason_for_dropping_the_criteria_crosses_too(tmp_path: Path, hub: Serving) -> None:
    """`no_evidence` is the other half of the same field and was dropped by the same line. A
    card whose criteria stopped applying is a real close, and it has to be sayable remotely."""
    card = plan(hub.root, [{"title": "obsolete", "spec": "s",
                            "acceptance": ["WHEN x THE SYSTEM SHALL y"]}],
                actor="dev:berna")["created"][0]["id"]
    mine = machine(tmp_path / "mine", hub.url)
    next_task(mine, actor="agent:berna/one", task=card)
    update(mine, card, actor="agent:berna/one", status="review", comment="handed over")

    update(mine, card, actor="dev:ana", status="done", no_code=True, comment="dropped",
           no_evidence="the feature was cut; the criterion describes something that is gone")

    assert ask(hub.root, card)["task"]["status"] == "done"


def test_a_teammates_board_stops_offering_a_card_somebody_is_holding(tmp_path: Path,
                                                                     hub: Serving) -> None:
    """Found the first time three clones shared one board. A claim records its own kind, and
    replay did not know that kind meant a status — so a card one developer was working on read
    `ready` on everybody else's machine. The claim was never at risk (writes route here, so two
    machines cannot both win one), but every other board OFFERED work already in hand, and the
    sweep turned that into "dispatch this". Bad advice from a stale replica is still bad advice.
    """
    card = the_card(hub.root)
    mine, theirs = machine(tmp_path / "mine", hub.url), machine(tmp_path / "theirs", hub.url)
    next_task(mine, actor="agent:berna/one", task=card)

    pull(theirs)

    assert ask(theirs, card)["task"]["status"] == "claimed"
    assert card not in {item["task"]["id"] for item in attention(theirs)["waiting"]}


def test_a_lease_that_expired_here_frees_the_card_everywhere(tmp_path: Path,
                                                             hub: Serving) -> None:
    """The other half, and it only became necessary because of the test above: now that a
    `claimed` replays, an expiry that stayed local would strand every teammate showing a card as
    held by an agent that died fifteen minutes ago, with nothing to ever tell them otherwise."""
    from taskops._clock import LEASE_TTL
    from taskops.engine import sweep_dead

    card = the_card(hub.root)
    mine, theirs = machine(tmp_path / "mine", hub.url), machine(tmp_path / "theirs", hub.url)
    next_task(mine, actor="agent:berna/one", task=card)
    pull(theirs)

    with Store(hub.root) as store:            # the worker goes silent past its TTL
        sweep_dead(store, at=time.time() + LEASE_TTL + 1)
    pull(theirs)

    assert ask(theirs, card)["task"]["status"] == "ready"


def test_handing_a_card_over_remotely_lets_go_of_the_lease_here_too(tmp_path: Path,
                                                                    hub: Serving) -> None:
    """`LEASE_ENDS` was written down twice and the copies drifted: the transition gained
    `review`, the mirror that a remote write updates did not. So a developer who handed a card
    over kept a live lease on it forever, their own board read that lease as "somebody is
    working on this", and the sweep went silent about a card waiting for a reviewer — and about
    the same card when it came back rejected. Found by running three clones, twice."""
    from taskops._clock import now

    card = the_card(hub.root)
    mine = machine(tmp_path / "mine", hub.url)
    next_task(mine, actor="agent:berna/one", task=card)

    update(mine, card, actor="agent:berna/one", status="review", comment="over to you")

    with Store(mine) as store:
        assert store.leases.live(now()) == [], "the handover let go of it here as well"
    assert {item["move"] for item in attention(mine)["waiting"]} == {"verify"}

    update(mine, card, actor="dev:ana", status="ready",
           comment="criterion 2 fails on an empty file")
    bounced = {item["task"]["id"] for item in attention(mine)["waiting"]}
    assert card in bounced, "a rejected card is waiting on somebody, not silently held"


def test_a_pulled_board_survives_losing_its_cache(tmp_path: Path, hub: Serving) -> None:
    """`db.sqlite` is documented as disposable — delete it, `taskops sync` rebuilds it from the
    log. That was true for git-synced projects and false for remote ones: `relay` stores a
    server's events marked exported so they are never echoed back, and the cost was that they
    reached the database and nothing else. Deleting the cache, the documented repair, emptied
    the board instead. It is also the stated architecture broken — nothing may hold state that
    is not derived from the log — so the log is what got fixed."""
    plan(hub.root, [{"title": "planned on the server", "spec": "s"}], actor="dev:berna")
    mine = machine(tmp_path / "mine", hub.url)
    pull(mine)

    (mine / ".taskops" / "db.sqlite").unlink()
    sync(mine)

    titles = {card["task"]["title"] for column in board(mine)["columns"]
              for card in column["cards"]}
    assert "planned on the server" in titles, "the log had to carry what the server sent"


def test_join_is_the_whole_onboarding(tmp_path: Path, hub: Serving) -> None:
    """One pasted URL — the string the server itself prints — replaces init + remote add +
    a token handed around in a chat. It has to end on a WORKING board: the first pull is part
    of joining, or the command ends on a promise instead of on the answer."""
    from taskops.usecases import join

    plan(hub.root, [{"title": "already on the board", "spec": "s"}], actor="dev:berna")
    where = tmp_path / "newcomer"
    init(where, install_git_hooks=False)     # a fresh clone's state, minus git

    done = join(where, f"{hub.url}?token={TOKEN}")

    assert not done.needs_login
    titles = {card["task"]["title"] for column in board(where)["columns"]
              for card in column["cards"]}
    assert "already on the board" in titles, "joining ends looking at the board"


def test_attention_answers_for_the_team_not_for_one_clone(tmp_path: Path,
                                                          hub: Serving) -> None:
    """The verb that opens every turn pulls first. Without that, "open with attention" answers
    from whatever this machine last saw — which in the simulacro meant a manager staring at
    "nothing is waiting" while a developer's handover sat on the server."""
    card = the_card(hub.root)
    mine, theirs = machine(tmp_path / "mine", hub.url), machine(tmp_path / "theirs", hub.url)
    next_task(mine, actor="agent:berna/one", task=card)
    update(mine, card, actor="agent:berna/one", status="review", comment="over to you")

    waiting = attention(theirs)["waiting"]       # no pull anywhere in sight

    assert [item["move"] for item in waiting if item["task"]["id"] == card] == ["verify"]


def test_a_plan_executes_in_the_servers_store_not_in_the_clones(tmp_path: Path,
                                                                hub: Serving) -> None:
    """THE single-source property. A plan on a remote project runs on the server via rpc, so
    a teammate sees it with no push, no pull and no cursor in between — there is nothing to
    carry, because it was never anywhere else."""
    mine, theirs = machine(tmp_path / "mine", hub.url), machine(tmp_path / "theirs", hub.url)

    plan(mine, [{"title": "born on the server", "spec": "s"}], actor="dev:berna")

    titles = {card["task"]["title"] for column in board(theirs)["columns"]
              for card in column["cards"]}
    assert "born on the server" in titles


def test_a_write_never_falls_back_to_local_when_the_server_is_down(tmp_path: Path) -> None:
    """The asymmetry that keeps one truth. A write that "fell back to local" on a network
    blip would fork the board precisely when nobody is watching — so it refuses, naming the
    URL, exactly as a claim always has."""
    where = tmp_path / "mine"
    init(where, install_git_hooks=False)
    add_remote(where, "http://127.0.0.1:1", "t0k3n")

    with pytest.raises(Exception, match="could not reach"):
        plan(where, [{"title": "must not land here"}], actor="dev:berna")
    assert all(not column["cards"] for column in _local_board(where)["columns"])


def test_a_read_degrades_to_the_cache_when_the_server_is_down(tmp_path: Path,
                                                              hub: Serving) -> None:
    """The other half of the asymmetry: refusing to READ without the server would make it a
    single point of failure for looking at your own last-known board."""
    from taskops.usecases import remove_remote

    mine = machine(tmp_path / "mine", hub.url)
    pull(mine)                                    # the cache knows the card
    remove_remote(mine)
    add_remote(mine, "http://127.0.0.1:1", "t0k3n")

    titles = {card["task"]["title"] for column in board(mine)["columns"]
              for card in column["cards"]}
    assert "the one card" in titles, "the last-known board still answers"


def _local_board(where: Path):
    """The clone's own cache, read around the router — what a fallback WOULD show."""
    from taskops.engine import board as build_board
    from taskops.storage import Store

    with Store(where) as store:
        return build_board(store)


def test_the_servers_log_is_never_the_empty_file_again(tmp_path: Path, hub: Serving) -> None:
    """Found on the box: four production boards, full databases, `events.jsonl` at exactly 0
    bytes — while the architecture calls the log truth and the database disposable. Two writers,
    neither exporting: the server's own use cases left events unexported with nothing running
    the exporter, and relayed arrivals came marked exported and were skipped by design. After
    the single-source refactor retired the clones' logs, that empty file was one `rm db.sqlite`
    from total loss."""
    from taskops.storage import read_log

    card = plan(hub.root, [{"title": "must reach the journal", "spec": "s"}],
                actor="dev:berna")["created"][0]["id"]
    mine = machine(tmp_path / "mine", hub.url)
    next_task(mine, actor="agent:berna/one", task=card)     # a write through the wire

    logged = {event["id"] for event in read_log(hub.root)}
    with Store(hub.root) as store:
        stored = {event["id"] for event in store.events.all()
                  if event["kind"] not in ("activity", "chat")}
    assert stored, "the premise: the database saw events"
    assert stored <= logged, "every durable event is in the file the moment the request ends"


def test_reconcile_backfills_a_board_with_a_full_database_and_an_empty_log(
        hub: Serving) -> None:
    """The repair for every board that predates the journal. The `exported` flag is ignored on
    purpose: it means "the git path sent this", and on a server that path never ran — trusting
    it is exactly how the four boards got this way."""
    from taskops.storage import LOG_FILE, read_log
    from taskops.usecases.journal import reconcile

    plan(hub.root, [{"title": "history", "spec": "s"}], actor="dev:berna")
    (hub.root / LOG_FILE).write_text("", encoding="utf-8")      # the box, as found

    backfilled = reconcile(hub.root)

    assert backfilled > 0
    assert {e["kind"] for e in read_log(hub.root)} >= {"created"}
    assert reconcile(hub.root) == 0, "idempotent — a healthy board writes nothing"
