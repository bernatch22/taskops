"""What a session is told about the OTHER sessions — the paragraph that stops collisions.

Everything else a session opens with describes its own state, so two sessions on one board each
behaved as though they were alone. That is not a theory: one card was implemented twice and one
review was started by two devs at once, and in both cases each session could see the whole board
and none of them could see each other.

The brief is small on purpose — who is connected, what they are holding, and nothing else. A
session that has to read history before choosing a card will not read it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from taskops.render.opening import render_opening
from taskops.usecases import init, next_task, plan, team_now, update
from taskops.usecases.opening import opening
from taskops.usecases.session import brief


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "b@example.com"),
                 ("config", "user.name", "Berna")):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    init(tmp_path)
    return tmp_path


def here(repo: Path, *devs: str) -> None:
    """Open a session for each dev — presence means a session, not a passing call."""
    for dev in devs:
        brief(repo, actor=dev, session=f"s-{dev}")


def two_cards(repo: Path) -> list[str]:
    made = plan(repo, [{"title": "El parser de fechas", "spec": "s"},
                       {"title": "El endpoint de export", "spec": "s"}], actor="dev:uno")
    return [card["id"] for card in made["created"]]


def test_a_dev_is_told_who_else_is_here_and_what_they_hold(repo: Path) -> None:
    first, second = two_cards(repo)
    here(repo, "dev:uno", "dev:dos")
    next_task(repo, task=first, actor="agent:uno/w1")
    next_task(repo, task=second, actor="agent:dos/w1")

    mates = team_now(repo, actor="dev:uno")
    assert [mate["dev"] for mate in mates["others"]] == ["dos"]
    assert mates["others"][0]["holding"] == [(second, "El endpoint de export")]


def test_a_session_is_never_told_it_might_collide_with_itself(repo: Path) -> None:
    """A dev and their agents are ONE person. Listing `agent:uno/w1` back to `dev:uno` would
    report a colleague who is actually this session's own sub-agent — and the whole point of
    the brief is deciding what NOT to touch."""
    first, _ = two_cards(repo)
    next_task(repo, task=first, actor="agent:uno/w1")

    assert team_now(repo, actor="dev:uno")["others"] == []
    assert team_now(repo, actor="agent:uno/w2")["others"] == []


def test_a_dev_who_stopped_calling_stops_being_listed(repo: Path) -> None:
    """Presence is a window, not a registration. A colleague who closed their laptop must not
    keep a card fenced off for the rest of the day."""
    from taskops.engine.routereview import PRESENCE_WINDOW
    from taskops.storage import Store

    two_cards(repo)
    here(repo, "dev:dos")
    assert [mate["dev"] for mate in team_now(repo, actor="dev:uno")["others"]] == ["dos"]

    with Store(repo) as store:
        store.db.execute("UPDATE presence SET last_seen = last_seen - ?",
                         (PRESENCE_WINDOW + 60,))
        store.db.commit()
    assert team_now(repo, actor="dev:uno")["others"] == []


def test_the_opening_says_it_before_it_says_what_is_waiting(repo: Path) -> None:
    """The ordering IS the argument: a session that reads the work list first starts choosing,
    and a session that reads who else is here first chooses differently."""
    first, second = two_cards(repo)
    here(repo, "dev:uno", "dev:dos")
    next_task(repo, task=first, actor="agent:uno/w1")
    next_task(repo, task=second, actor="agent:dos/w1")

    text = render_opening(opening(repo, actor="dev:uno"))
    assert "El endpoint de export" in text, "the TITLE, not just an id — an id says nothing"
    assert text.index("Who else is on this board") < text.index("Waiting on a decision")


def test_working_alone_is_silent_rather_than_announced(repo: Path) -> None:
    """A heading over an empty list would tell somebody they are alone on every session they
    ever open, which is most of them. Nobody reads a paragraph that is always the same."""
    two_cards(repo)
    assert "Who else is on this board" not in render_opening(opening(repo, actor="dev:uno"))


def test_the_opening_hides_a_review_routed_to_somebody_else(repo: Path) -> None:
    """The sweep in the opening used to run with no actor, so it listed every review on the
    board — including the ones this dev is forbidden to close and the ones routed elsewhere.
    Advice the engine will refuse costs calls and teaches the reader to distrust the list."""
    from taskops.usecases import context_state

    context_state(repo, "decision", "reviewer: peer — nos revisamos", actor="dev:uno")
    here(repo, "dev:uno", "dev:dos")
    card, _ = two_cards(repo)
    next_task(repo, task=card, actor="agent:uno/w1")
    update(repo, card, status="review", comment="listo", actor="agent:uno/w1")

    assert card in render_opening(opening(repo, actor="dev:dos")), "its reviewer must see it"
    assert card not in render_opening(opening(repo, actor="dev:tres"))
