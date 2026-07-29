"""The activity projection: the log read as a history.

Every assertion here is about a claim the view makes to a person reading it — the order it implies,
what a count means, and whether it admits to having stopped early. A history that is wrong about any
of those is worse than no history, because nobody can tell from the screen.
"""

from __future__ import annotations

from taskops.contracts import Task
from taskops.engine import record
from taskops.engine.history import activity
from taskops.storage import Store


def _log(store: Store, task: str, actor: str, kind: str, ts: float,
         **body: object) -> None:
    record(store, task=task, actor=actor, kind=kind, body=body, ts=ts)


def test_the_timeline_is_newest_first(store: Store) -> None:
    """The log's own order is oldest-first, and a timeline read from the top wants the opposite."""
    for index in range(5):
        _log(store, "tk-1", "dev:berna", "comment", 1_000.0 + index, text=f"m{index}")
    stamps = [event["ts"] for event in activity(store, since=0.0)["events"]]
    assert stamps == sorted(stamps, reverse=True)


def test_an_actor_is_ranked_by_tasks_touched_not_by_noise(store: Store) -> None:
    """Forty comments on one card is less work than four cards closed, and counting events would
    put the noisy actor on top — which is the ranking that makes the whole panel untrustworthy."""
    for index in range(40):
        _log(store, "tk-1", "dev:loud", "comment", 1_000.0 + index, text="…")
    for index in range(4):
        _log(store, f"tk-{index}", "dev:quiet", "done", 2_000.0 + index, to="done")

    rolls = {roll["actor"]: roll for roll in activity(store, since=0.0)["actors"]}
    assert [roll["actor"] for roll in activity(store, since=0.0)["actors"]][0] == "dev:quiet"
    assert rolls["dev:quiet"]["tasks"] == 4
    assert rolls["dev:loud"]["tasks"] == 1
    assert rolls["dev:loud"]["comments"] == 40


def test_a_close_is_counted_from_its_own_kind(store: Store) -> None:
    """`update` writes `done` rather than `status` when the target is done, precisely so a close can
    be found without reading bodies. Counting `status` events instead reports zero closes on a
    project where everything was closed — which is what it did."""
    _log(store, "tk-1", "agent:berna/one", "done", 1_000.0, **{"from": "claimed", "to": "done"})
    _log(store, "tk-2", "agent:berna/one", "status", 1_001.0, **{"from": "ready", "to": "review"})
    roll = activity(store, since=0.0)["actors"][0]
    assert roll["done"] == 1


def test_the_window_excludes_what_is_behind_it(store: Store) -> None:
    _log(store, "tk-1", "dev:berna", "comment", 1_000.0, text="old")
    _log(store, "tk-1", "dev:berna", "comment", 5_000.0, text="new")
    kept = activity(store, since=2_000.0)["events"]
    assert [event["body"]["text"] for event in kept] == ["new"]


def test_truncation_is_admitted_and_keeps_the_END(store: Store) -> None:
    """A slice shown as if it were everything is the failure mode of every capped view. It keeps the
    newest, because that is what a history is opened for."""
    for index in range(10):
        _log(store, "tk-1", "dev:berna", "comment", 1_000.0 + index, text=f"m{index}")
    capped = activity(store, since=0.0, limit=3)
    assert capped["truncated"]
    assert [event["body"]["text"] for event in capped["events"]] == ["m9", "m8", "m7"]


def test_titles_ride_along_with_the_timeline(store: Store) -> None:
    """Fetching a title per row would be a hundred requests to render one screen."""
    store.tasks.insert(Task(id="tk-1", title="The one thing", spec="", status="ready",
                            priority=2, parent=None, labels=[], files=[], assignee="", reviewer="",
                            created_by="dev:berna", created=1.0, updated=1.0))
    _log(store, "tk-1", "dev:berna", "comment", 1_000.0, text="hi")
    assert activity(store, since=0.0)["titles"] == {"tk-1": "The one thing"}
