"""The milestone fold, and the legacy mapping that keeps a 0.4.0 board readable.

Written against real SQLite through `store.events.append`, not against a list of literals: the
fold reads through `of_task`, which orders by `(ts, seq)`, and the legacy election depends on that
order being right — "the LATEST project objective becomes the chapter in force" is a statement
about the log's order, so a test that handed the fold a pre-sorted Python list would pin nothing.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from taskops._ids import event_id
from taskops.contracts import Event
from taskops.contracts.context import CONTEXT_KIND, CONTEXT_TASK
from taskops.contracts.milestone import MILESTONE_KIND, Milestone
from taskops.storage import Store
from taskops.storage.milestone import active, milestones, one, planned
from tests.conftest import CLOCK
from tests.contracts.shape import assert_shape


@pytest.fixture()
def store(bare: "Path") -> "Iterator[Store]":
    """A store over `bare` — the board with NO chapter open.

    Not the shared `store` fixture, which is built on `root` and opens one so that `plan` works.
    Every test here counts milestones (`(found,) = milestones(store)`, `active(store) == [a, b]`),
    so a chapter it did not write is an off-by-one in nineteen assertions. The fold is what is
    under test; a board that already has a chapter is a different subject.
    """
    with Store(bare) as opened:
        yield opened


# ---- writing events by hand

_TICK = 0


def _at(store: Store, kind: str, actor: str, body: dict[str, Any]) -> str:
    """Append one event and return its id. Each call gets a LATER ts, so log order is the order
    these are written in — which is what the fold reads and what the election depends on."""
    global _TICK
    _TICK += 1
    ts = CLOCK + _TICK
    event = Event(id=event_id(task=CONTEXT_TASK, actor=actor, kind=kind, body=body, ts=ts),
                  task=CONTEXT_TASK, actor=actor, kind=kind, body=body, ts=ts)
    store.events.append(event)
    return event["id"]


def _create(store: Store, text: str, *, planned_: bool = False, horizon: str = "",
            actor: str = "agent:berna/w1") -> str:
    return _at(store, MILESTONE_KIND, actor,
               {"op": "create", "text": text, "horizon": horizon, "planned": planned_})


def _move(store: Store, target: str, to: str, *, actor: str = "dev:berna", m: str = "") -> str:
    return _at(store, MILESTONE_KIND, actor, {"op": "move", "milestone": target, "to": to, "m": m})


def _objective(store: Store, text: str, *, owner: str = "", actor: str = "dev:berna",
               level: str | None = None) -> str:
    """A context objective. `level=None` writes NO level field — which is what makes it LEGACY."""
    body: dict[str, Any] = {"sort": "objective", "text": text, "labels": [], "files": [],
                            "horizon": "", "owner": owner}
    if level is not None:
        body["level"] = level
    return _at(store, CONTEXT_KIND, actor, body)


# ---- the ops


def test_a_create_event_is_the_milestone_and_its_id(store: Store) -> None:
    """The id is the CREATE event's content hash — the whole reason a fact written on one clone
    can attach to a chapter created on another."""
    made = _create(store, "que una clienta suba su CSV", horizon="2026-08-20")
    (found,) = milestones(store)
    # A TypedDict is erased at runtime, so the fold could quietly put a float where a string
    # belongs and nothing would complain until a renderer joined it.
    assert_shape(found, Milestone)
    assert found["id"] == made
    assert found["text"] == "que una clienta suba su CSV"
    assert found["horizon"] == "2026-08-20"
    assert found["state"] == "in_force"
    assert found["created_by"] == "agent:berna/w1"
    assert (found["closed_by"], found["note"]) == ("", "")


def test_planned_in_the_body_means_it_does_not_start(store: Store) -> None:
    _create(store, "que pueda facturar", planned_=True)
    assert [m["state"] for m in milestones(store)] == ["planned"]
    assert [m["text"] for m in planned(store)] == ["que pueda facturar"]
    assert active(store) == []


def test_an_update_rewrites_only_the_fields_it_names(store: Store) -> None:
    """An absent field means "leave it", never "blank it": `edit --text` must not erase a horizon
    somebody set from the other surface."""
    made = _create(store, "el importador", horizon="2026-08-20")
    _at(store, MILESTONE_KIND, "dev:berna", {"op": "update", "milestone": made, "text": "el CSV"})
    (found,) = milestones(store)
    assert (found["text"], found["horizon"]) == ("el CSV", "2026-08-20")
    assert found["updated"] > found["created"]


def test_a_move_carries_its_message_and_the_state(store: Store) -> None:
    made = _create(store, "el importador")
    _move(store, made, "review", actor="agent:berna/w1", m="siete de siete cerradas")
    (found,) = milestones(store)
    assert found["state"] == "review"
    assert found["note"] == "siete de siete cerradas"


def test_a_move_naming_an_unknown_milestone_is_skipped(store: Store) -> None:
    """Events arrive out of order when a `git pull` merges two ends of a log, and a move can land
    before the create it refers to. Skipping is the log reader's standing contract."""
    _move(store, "deadbeef", "reached")
    assert milestones(store) == []


def test_an_op_this_version_cannot_read_is_skipped(store: Store) -> None:
    made = _create(store, "el importador")
    _at(store, MILESTONE_KIND, "dev:berna", {"op": "teleport", "milestone": made, "to": "reached"})
    _at(store, MILESTONE_KIND, "dev:berna", {"op": "move", "milestone": made, "to": "sideways"})
    assert [m["state"] for m in milestones(store)] == ["in_force"]


def test_nothing_moves_a_chapter_back_to_planned(store: Store) -> None:
    made = _create(store, "el importador")
    _move(store, made, "planned")
    assert [m["state"] for m in milestones(store)] == ["in_force"]


# ---- who closed it, which is the point of the whole model


def test_review_leaves_closed_by_empty_and_reached_fills_it(store: Store) -> None:
    """The distinction the model exists for. An agent reporting a chapter finished writes a NOTE
    and no verifier; the person who agrees writes the verifier. If `review` filled `closed_by`,
    "somebody says it is done" and "somebody who is not the author agrees" would be one record.
    """
    made = _create(store, "el importador")
    _move(store, made, "review", actor="agent:berna/w1", m="listo")
    assert one(store, made) is not None
    assert one(store, made)["closed_by"] == ""       # type: ignore[index]
    _move(store, made, "reached", actor="dev:ana", m="verificado")
    closed = one(store, made)
    assert closed is not None
    assert (closed["state"], closed["closed_by"]) == ("reached", "dev:ana")


def test_abandoned_also_records_who_stopped_it(store: Store) -> None:
    """"We stopped" is not "we shipped", and the record has to be able to tell them apart — which
    it can only do if both carry the person who said so."""
    made = _create(store, "el importador")
    _move(store, made, "abandoned", actor="dev:berna", m="el cliente lo canceló")
    closed = one(store, made)
    assert closed is not None
    assert (closed["state"], closed["closed_by"], closed["note"]) == (
        "abandoned", "dev:berna", "el cliente lo canceló")


# ---- several active at once


def test_several_chapters_are_active_at_the_same_time(store: Store) -> None:
    """The correction 0.5.0 makes to its own design note. Forcing one of two things a team is
    demonstrably working on into `planned` would be the board lying about what is happening."""
    first = _create(store, "el importador")
    second = _create(store, "las facturas")
    third = _create(store, "el mailing", planned_=True)
    fourth = _create(store, "el viejo")
    _move(store, first, "review", actor="agent:berna/w1")
    _move(store, fourth, "reached", actor="dev:berna")
    assert [m["id"] for m in active(store)] == [first, second]
    assert [m["id"] for m in planned(store)] == [third]


def test_milestones_come_back_in_creation_order(store: Store) -> None:
    """Not state order: #1 #2 #3 has to mean what it means in docs/milestones.md, and grouping by
    state is a renderer's decision."""
    ids = [_create(store, f"chapter {n}") for n in range(4)]
    _move(store, ids[0], "reached", actor="dev:berna")
    assert [m["id"] for m in milestones(store)] == ids


# ---- prefixes


def test_a_prefix_names_a_chapter_the_way_it_is_printed(store: Store) -> None:
    """Every renderer prints eight characters, so the string a person can SEE is the only one they
    can retype — the same reason `context retire` accepts one."""
    made = _create(store, "el importador")
    found = one(store, made[:8])
    assert found is not None and found["id"] == made
    assert one(store, f"  {made[:8]}  ") is not None      # trimmed, like a pasted id


def test_an_ambiguous_prefix_resolves_to_nothing(store: Store) -> None:
    """None for "two chapters start with that" as well as for "no such chapter": this layer may
    not pick between two, and the caller writes the refusal that names both."""
    # Thirty hex ids over sixteen first characters: by pigeonhole two of them share one, so this
    # is deterministic rather than lucky.
    ids = sorted(_create(store, f"chapter {n}") for n in range(30))
    shared = next(a[:1] for a, b in zip(ids, ids[1:], strict=False) if a[:1] == b[:1])
    assert one(store, shared) is None
    assert one(store, "zzzzzzzz") is None


# ---- legacy: the election, per NEW_VERSION.md §2


def test_old_project_objectives_become_chapters_the_latest_in_force(store: Store) -> None:
    """A pre-0.5.0 board is NOT reset — one server board carries 336 events of real history. An
    objective with no owner WAS the project's north, superseded by stating a newer one, which is
    exactly a chapter that ended. So the latest is in force and the earlier ones are `reached`.
    """
    first = _objective(store, "que el board no mienta")
    second = _objective(store, "que una clienta suba su CSV")
    found = milestones(store)
    assert [(m["id"], m["state"]) for m in found] == [(first, "reached"), (second, "in_force")]
    assert [m["id"] for m in active(store)] == [second]


def test_an_elected_chapter_has_no_verifier_because_the_record_cannot_invent_one(
        store: Store) -> None:
    """`closed_by` stays empty on every reached-by-election chapter. Filling it with the actor who
    wrote the objective would record that somebody verified work nobody verified — and the whole
    model rests on that field meaning a second person agreed."""
    _objective(store, "lo primero", actor="dev:berna")
    _objective(store, "lo segundo", actor="dev:ana")
    closed = [m for m in milestones(store) if m["state"] == "reached"]
    assert [m["closed_by"] for m in closed] == [""]
    assert [m["created_by"] for m in closed] == ["dev:berna"]     # who WROTE it is kept


def test_a_dev_s_own_objective_is_not_elected(store: Store) -> None:
    """An objective with an OWNER is that dev's and stays a fact. Electing it would turn "I am on
    the parser this week" into the team's chapter."""
    _objective(store, "el parser de fechas", owner="dev:ana")
    assert milestones(store) == []


def test_a_retired_objective_does_not_come_back_as_a_chapter(store: Store) -> None:
    """A north somebody explicitly withdrew must not be resurrected by a version change."""
    gone = _objective(store, "lo que abandonamos")
    _at(store, CONTEXT_KIND, "dev:berna", {"retires": gone})
    kept = _objective(store, "lo que seguimos")
    assert [m["id"] for m in milestones(store)] == [kept]


def test_the_election_is_inert_once_facts_declare_a_level(store: Store) -> None:
    """The discriminator is `level` being ABSENT. A 0.5.0 writer always states one, so a board
    written after the model existed cannot have a fact elected into a chapter behind its back."""
    _objective(store, "el parser", level="milestone")
    _objective(store, "una regla del proyecto", level="project")
    assert milestones(store) == []


def test_a_real_milestone_and_an_elected_one_coexist(store: Store) -> None:
    """The election does not stand down when real chapters exist, and it must not: several active
    is legal, and the board's old north is a chapter a person can now verify or abandon."""
    old = _objective(store, "el viejo norte")
    made = _create(store, "el importador")
    assert {m["id"] for m in active(store)} == {old, made}
