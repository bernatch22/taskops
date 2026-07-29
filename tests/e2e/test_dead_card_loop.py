"""The impossible-card loop, closed at both ends.

One card with a title and no spec collected two dispatched workers and two releases in a single
day. Each agent behaved correctly — it could not do anything but guess, and it refused to guess.
The system was wrong twice: it let a worker be sent to a card no worker could act on, and when
the worker handed it back, the assignee stayed — so the card read as somebody's, was invisible
to everyone else, and drew the next dispatch straight back into the loop.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskops._errors import BadRequest
from taskops.usecases import dispatch, next_task, plan, update


def test_a_release_hands_the_card_back_to_the_pool(root: Path) -> None:
    """Back means BACK: the assignee is cleared, so anyone can take it — including, if it
    wants, the agent that released it. Ready is ready."""
    made = plan(root, [{"title": "the work", "spec": "real"}], actor="dev:ana")["created"][0]
    dispatch(root, tasks=(made["id"],), actor="dev:ana")
    next_task(root, task=made["id"], actor="agent:ana/w1")

    update(root, made["id"], status="released", comment="out of my depth",
           actor="agent:ana/w1")

    other = next_task(root, task=made["id"], actor="agent:ana/w2")
    assert other["claim"] is not None, "a released card must be claimable by ANYBODY"


def test_a_spec_less_card_is_never_dispatched(root: Path) -> None:
    """A worker is a model spending money unsupervised; handed a title alone it can only guess
    or give up. The skip is reported, never silent — a dispatch that quietly dropped a card
    would read as a broken dispatch."""
    bare = plan(root, [{"title": "rate limit"}], actor="dev:ana")["created"][0]
    full = plan(root, [{"title": "other", "spec": "real"}], actor="dev:ana")["created"][0]

    done = dispatch(root, tasks=(bare["id"], full["id"]), actor="dev:ana")
    assert [w.task for w in done.launched] == [full["id"]]
    assert bare["id"] in done.skipped

    pooled = dispatch(root, count=5, actor="dev:ana")
    assert bare["id"] not in [w.task for w in pooled.launched]


def test_the_api_refuses_to_assign_a_spec_less_card_to_an_agent(root: Path) -> None:
    """Same guard at the other door — and only for agents. A PERSON may take a spec-less card:
    they can ask, and they are not billed by the turn."""
    from taskops.transports.http.assigning import _assign

    bare = plan(root, [{"title": "rate limit"}], actor="dev:ana")["created"][0]
    # a full agent id, because a bare registry name would be refused earlier for other reasons
    with pytest.raises(BadRequest, match="tasks edit"):
        _assign(root, bare["id"], "agent:ana/w1")

    told = _assign(root, bare["id"], "dev:ana")
    assert told["assignee"] == "dev:ana", "a person may still take it"
