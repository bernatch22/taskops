"""Replay puts a card's chapter on the row, or leaves it without one.

`engine.replay` is what makes the log the source of truth rather than a diary: a teammate's
`git pull` delivers `created` events and this is what turns them into rows. A field the event
carries and replay drops is a field that exists on the machine that wrote the card and nowhere
else — which is precisely the bug class that made a `git pull` import events and leave an empty
board.
"""

from __future__ import annotations

from typing import Any

from taskops._ids import event_id
from taskops.contracts import Event
from taskops.engine import replay
from taskops.storage import Store
from tests.conftest import CLOCK


def _created(task_id: str, **body: Any) -> Event:
    full: dict[str, Any] = {"title": "el lector de CSV", "spec": "", "priority": 2,
                            "parent": None, "labels": [], "files": [], "assignee": "",
                            "reviewer": "", **body}
    return Event(id=event_id(task=task_id, actor="dev:ana", kind="created", body=full, ts=CLOCK),
                 task=task_id, actor="dev:ana", kind="created", body=full, ts=CLOCK)


def test_a_card_arrives_carrying_its_chapter(store: Store) -> None:
    """A card belongs to exactly one milestone, and that is what bounds the facts its worker
    reads — so it has to survive the trip between machines."""
    replay.apply(store, [_created("tk-aaaaaa", milestone="7c1a44b2")])
    assert store.tasks.need("tk-aaaaaa")["milestone"] == "7c1a44b2"


def test_a_card_planned_before_chapters_existed_arrives_with_none(store: Store) -> None:
    """And it is NOT attached to whichever chapter happens to be open on this clone. That would
    invent a fact about the past, and — worse — invent a different one on every machine, since
    which chapter is open when a `sync` runs is a property of the machine and not of the card.
    """
    replay.apply(store, [_created("tk-bbbbbb")])
    assert store.tasks.need("tk-bbbbbb")["milestone"] == ""
