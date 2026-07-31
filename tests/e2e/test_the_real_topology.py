"""The whole thing, in the shape a team actually has — and the only test that could have caught
the twelve failures found by running it instead.

Every bug of the last three live runs shared one property: **none of them was a bug in the
logic.** Each lived in a seam between two machines, and every test in this suite ran one repo,
one process, one store. The list, and where each one hid:

    the server ran the merge (it has no checkout)            client ↔ server
    the landing was recorded in the local cache, not the board  client ↔ server
    the reviewer's clone had never seen the branch           clone ↔ clone
    a rejected push still reported `landed ok`               clone ↔ origin
    `join` left every clone permanently dirty                clone ↔ origin
    the session id never reached the store that routes       client ↔ server

So this file builds the seam: a real HTTP server on a real port holding the board, a BARE
origin, and two clones that each ran `taskops join` — with `.taskops/` living only on the
server, exactly like a real project. Then it walks a card from plan to trunk and asserts the
thing a person actually checks: **the work is in the shared trunk and the board says so.**

It is slow, and that is the price of testing the deployment rather than the module. There is
one of it on purpose.
"""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import Iterator

import pytest

from taskops.transports.http import bound_port, serve_route
from taskops.transports.http.projects import mount
from taskops.transports.cli.commands._serve_init import create
from taskops.engine import branch_for
from taskops.usecases import next_task, plan, update
from taskops.usecases.attention import attention
from taskops.usecases.context import state as context_state
from taskops.usecases.join import join
from taskops.usecases.opening import opening

# ruff: noqa: I001

BOARD = "equipo"


def git(where: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=where, capture_output=True, text=True, check=True)
    return done.stdout.strip()


class Team:
    """A server, a bare origin, and two developers who joined the board from their clones."""

    def __init__(self, url: str, token: str, origin: Path, uno: Path, dos: Path) -> None:
        self.url, self.token, self.origin, self.uno, self.dos = url, token, origin, uno, dos

    def trunk(self) -> str:
        return git(self.origin, "rev-parse", "main")

    def files_in_trunk(self) -> list[str]:
        return git(self.origin, "ls-tree", "-r", "--name-only", "main").splitlines()


@pytest.fixture
def team(tmp_path: Path) -> Iterator[Team]:
    server_home = tmp_path / "servidor"
    create(server_home, BOARD)
    token = (server_home / BOARD / "token").read_text(encoding="utf-8").strip()

    server = serve_route("127.0.0.1", 0, mount(server_home))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{bound_port(server)}/{BOARD}"

    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    seed = _seeded(tmp_path / "semilla", origin)

    clones = [_joined(tmp_path / name, origin, url, token) for name in ("uno", "dos")]
    try:
        yield Team(url, token, origin, *clones)
    finally:
        server.shutdown()
        server.server_close()
        del seed


def _seeded(where: Path, origin: Path) -> Path:
    """The trunk everybody starts from, with the taskops cache already ignored.

    A project whose board lives on a server keeps NOTHING of it in git, and that gitignore is
    load-bearing rather than tidy: without it every clone is permanently dirty and `git switch`
    refuses, so nothing can ever be merged. It cost a whole run to learn.
    """
    subprocess.run(["git", "clone", "-q", str(origin), str(where)], check=True)
    _identity(where)
    (where / "README.md").write_text("# equipo\n", encoding="utf-8")
    (where / ".gitignore").write_text(".taskops/\n.mcp.json\n.claude/settings.local.json\n"
                                      ".claude/agents/taskops-*.md\n", encoding="utf-8")
    git(where, "add", "-A")
    git(where, "commit", "-qm", "seed")
    git(where, "push", "-q", "origin", "main")
    return where


def _joined(where: Path, origin: Path, url: str, token: str) -> Path:
    subprocess.run(["git", "clone", "-q", str(origin), str(where)], check=True)
    _identity(where)
    join(where, f"{url}?token={token}")
    return where


def _identity(where: Path) -> None:
    for args in (("config", "user.email", "b@example.com"), ("config", "user.name", "Berna")):
        subprocess.run(["git", *args], cwd=where, check=True, capture_output=True)


def a_card(team: Team, title: str) -> str:
    """Planned by a MANAGER who never opens a session — the shape that produced a ghost
    reviewer once, and must never be routed to."""
    return str(plan(team.uno, [{"title": title, "spec": "hacelo",
                                "acceptance": [f"WHEN {title} THE SYSTEM SHALL andar"]}],
                    actor="dev:mgr")["created"][0]["id"])


def worked(clone: Path, card: str, title: str, *, actor: str, file: str) -> str:
    """A worker doing what a worker does: branch, commit, publish, hand over."""
    next_task(clone, task=card, actor=actor)
    branch = branch_for({"id": card, "title": title})       # type: ignore[arg-type]
    git(clone, "switch", "-qc", branch)
    (clone / file).write_text(f"el trabajo de {actor}\n", encoding="utf-8")
    git(clone, "add", file)
    git(clone, "commit", "-qm", f"[{card}] {title}")
    git(clone, "push", "-q", "origin", branch)
    git(clone, "switch", "-q", "main")
    return branch


def test_a_card_walks_from_a_plan_to_the_shared_trunk(team: Team) -> None:
    """The whole loop, across three machines, asserted where a person would look.

    Reading it top to bottom is the point: every line is a thing that was broken at some
    moment in the last three days, and none of them was visible from inside one repository.
    """
    context_state(team.uno, "decision", "reviewer: peer — nadie cierra la suya", actor="dev:mgr")
    opening(team.uno, session="s-uno", actor="dev:uno")
    opening(team.dos, session="s-dos", actor="dev:dos")

    card = a_card(team, "El primero")
    worked(team.uno, card, "El primero", actor="agent:uno/w1", file="uno.txt")
    handed = update(team.uno, card, status="review", comment="a revisar", actor="agent:uno/w1")

    assert handed["routed_to"] == "dev:dos", "the only other session open is the only candidate"

    mine = attention(team.dos, actor="dev:dos")["waiting"]
    assert card in {item["task"]["id"] for item in mine}
    assert card not in {item["task"]["id"] for item in attention(team.uno, actor="dev:uno")["waiting"]}

    # Claimed as `dev:dos`, which is the id that broke this live. Routing writes the
    # reviewer's DEV into `assignee`, so that claim matched the "worker coming back" test
    # beside it and pulled the card OUT of review — where every closing rule stops applying.
    # An `agent:` id never matched, so a test that only claimed through one hid the bug;
    # mutation testing is what said so. The agent path has its own test in `test_routing`.
    claimed = next_task(team.dos, task=card, actor="dev:dos")["claim"]
    assert claimed is not None
    assert claimed["view"]["task"]["status"] == "review", "checking it, not taking it back"

    closed = update(team.dos, card, status="done", comment="pasa", actor="dev:dos",
                    evidence="el criterio: verificado")
    assert closed["task"]["status"] == "done"

    assert "uno.txt" in team.files_in_trunk(), "landed means the SHARED trunk has it"
    assert _landing(team.dos, card) == {"ok": True}, "and the BOARD has to say so"


def test_both_developers_land_at_once_without_forking_the_trunk(team: Team) -> None:
    """Two cards, one each, closed back to back — the case that forked a real trunk.

    Each developer merges into their own copy, so the second one is landing onto a trunk that
    moved a minute ago. It reported success and pushed nothing, and the board said a card was
    in a trunk that had never seen it.
    """
    context_state(team.uno, "decision", "reviewer: peer — nadie cierra la suya", actor="dev:mgr")
    opening(team.uno, session="s-uno", actor="dev:uno")
    opening(team.dos, session="s-dos", actor="dev:dos")

    suyo = a_card(team, "El de uno")
    ajeno = a_card(team, "El de dos")
    worked(team.uno, suyo, "El de uno", actor="agent:uno/w1", file="uno.txt")
    worked(team.dos, ajeno, "El de dos", actor="agent:dos/w1", file="dos.txt")
    update(team.uno, suyo, status="review", comment="a revisar", actor="agent:uno/w1")
    update(team.dos, ajeno, status="review", comment="a revisar", actor="agent:dos/w1")

    update(team.dos, suyo, status="done", comment="pasa", actor="agent:dos/v1",
           evidence="el criterio: verificado")
    update(team.uno, ajeno, status="done", comment="pasa", actor="agent:uno/v1",
           evidence="el criterio: verificado")

    trunk = team.files_in_trunk()
    assert "uno.txt" in trunk and "dos.txt" in trunk, "neither developer's work is lost"
    for card in (suyo, ajeno):
        assert _landing(team.dos, card) == {"ok": True}, f"{card} says landed and is not"


def test_the_manager_who_never_opened_a_session_is_never_the_reviewer(team: Team) -> None:
    """`dev:mgr` plans every card here and never opens a session. A live board routed a review
    to exactly such a manager — present by every measure the store had, four minutes gone —
    and the card waited on somebody who was not coming back."""
    context_state(team.uno, "decision", "reviewer: peer — nadie cierra la suya", actor="dev:mgr")
    opening(team.dos, session="s-dos", actor="dev:dos")

    card = a_card(team, "El primero")
    worked(team.uno, card, "El primero", actor="agent:uno/w1", file="uno.txt")
    handed = update(team.uno, card, status="review", comment="a revisar", actor="agent:uno/w1")

    assert handed["routed_to"] == "dev:dos"


def _landing(clone: Path, card: str) -> dict[str, bool]:
    """What the BOARD says happened to this card's branch — not what the machine that merged
    it believes. Those were two different answers, and only one of them is the board's."""
    from taskops.usecases import ask

    events = ask(clone, card, actor="dev:dos")["history"]
    landed = [event for event in events if event["kind"] == "landed"]
    assert landed, f"{card} closed and nothing recorded a landing"
    return {"ok": bool(landed[-1]["body"].get("ok"))}


def test_a_push_the_remote_refuses_is_not_a_landing(team: Team) -> None:
    """The half of the landing fix that the two tests above do NOT cover, and mutation testing
    is what said so: with the trunk caught up, the push always succeeds, so deleting the check
    changed nothing and both tests stayed green.

    It matters in the window between the catch-up and the push — a genuine race, and racing is
    a bad way to assert. A remote that refuses on purpose reproduces the same fact in one line:
    the merge happened HERE and nowhere else, so `landed` would be a lie.
    """
    guard = team.origin / "hooks" / "pre-receive"
    guard.write_text("#!/bin/sh\necho 'este remoto dice que no' >&2\nexit 1\n", encoding="utf-8")
    guard.chmod(0o755)

    context_state(team.uno, "decision", "reviewer: peer — nadie cierra la suya", actor="dev:mgr")
    opening(team.uno, session="s-uno", actor="dev:uno")
    opening(team.dos, session="s-dos", actor="dev:dos")
    card = a_card(team, "El primero")

    next_task(team.uno, task=card, actor="agent:uno/w1")
    branch = branch_for({"id": card, "title": "El primero"})    # type: ignore[arg-type]
    git(team.uno, "switch", "-qc", branch)
    (team.uno / "uno.txt").write_text("el trabajo\n", encoding="utf-8")
    git(team.uno, "add", "uno.txt")
    git(team.uno, "commit", "-qm", f"[{card}] hecho")
    git(team.uno, "switch", "-q", "main")

    from taskops.usecases.land import land
    done = land(team.uno, branch)

    assert not done.ok, "merged locally is not landed — the shared trunk never saw it"
    assert "uno.txt" not in team.files_in_trunk()
