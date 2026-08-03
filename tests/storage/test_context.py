"""The fact projection at the layer that owns it: what `fact_of` makes of a body.

The compatibility questions are asserted HERE and not through `usecases.context.show`, because
they are properties of the fold: what a body with no `level` means, and what a body written by a
version this one has never seen means. A test at the use-case layer would pin the slice as well,
and the slice is a different decision that changes more often.
"""

from __future__ import annotations

from typing import Any

from taskops._ids import event_id
from taskops.contracts import Event
from taskops.contracts.context import CONTEXT_KIND, CONTEXT_TASK, Fact
from taskops.storage import Store
from taskops.storage.context import fact_of, facts, matching
from tests.conftest import CLOCK
from tests.contracts.shape import assert_shape


def _event(body: dict[str, Any], *, actor: str = "dev:berna", ts: float = CLOCK) -> Event:
    return Event(id=event_id(task=CONTEXT_TASK, actor=actor, kind=CONTEXT_KIND, body=body, ts=ts),
                 task=CONTEXT_TASK, actor=actor, kind=CONTEXT_KIND, body=body, ts=ts)


def _legacy(sort: str, **over: Any) -> dict[str, Any]:
    """A body exactly as a 0.4.0 taskops wrote it: seven fields, no `level`, no `milestone`."""
    return {"sort": sort, "text": "t", "labels": [], "files": [], "horizon": "",
            "owner": "", **over}


# ---- the two new fields


def test_a_fact_that_declares_its_level_keeps_it() -> None:
    """A lifetime declared where the fact is written, which is the whole model — so the projection
    must not re-derive it from anything."""
    found = fact_of(_event({**_legacy("rule"), "level": "milestone", "milestone": "abc123"}))
    assert found is not None
    assert_shape(found, Fact)
    assert (found["level"], found["milestone"]) == ("milestone", "abc123")


def test_rule_is_a_sort_again_and_is_not_remapped() -> None:
    """`rule` came back in 0.5.0 and it is NOT the `invariant` that was removed in 0.4.0: this one
    keeps its scope, because it is a name for a thing at either level rather than a lifetime
    wearing a sort's clothes."""
    found = fact_of(_event({**_legacy("rule", labels=["core"]), "level": "project"}))
    assert found is not None
    assert (found["sort"], found["labels"]) == ("rule", ["core"])


# ---- compatibility: a board written before levels existed


def test_a_fact_with_no_level_is_read_as_the_projects_and_stays_in_force() -> None:
    """THE legacy rule. A body with no `level` was written before levels existed, and it has no
    chapter to belong to — so it reads as `project`: permanent, attached to nothing that ends.

    Reading it as `milestone` (the default a WRITER gets today) would attach every standing fact
    on a 0.4.0 board to whichever chapter happens to be open now, and drop all of them from every
    slice the moment somebody verified that chapter. A board's standing rules may not vanish
    because a version changed — the same argument as the `invariant → decision` mapping, one field
    over.
    """
    found = fact_of(_event(_legacy("decision")))
    assert found is not None
    assert (found["level"], found["milestone"]) == ("project", "")


def test_a_level_this_version_cannot_read_falls_the_same_way() -> None:
    """A value a NEWER taskops wrote is one this one cannot place, and the safe failure is "still
    in force" rather than "silently gone"."""
    found = fact_of(_event({**_legacy("decision"), "level": "quarter"}))
    assert found is not None
    assert found["level"] == "project"


def test_the_invariant_mapping_from_0_4_0_is_untouched() -> None:
    """Pinned here as well as at the use-case layer, because 0.5.0 rewrote the function around it:
    an `invariant` still reads as a decision AND still loses its scope."""
    found = fact_of(_event(_legacy("invariant", labels=["core"], files=["a.py"])))
    assert found is not None
    assert (found["sort"], found["labels"], found["files"]) == ("decision", [], [])


def test_a_sort_a_newer_taskops_invented_is_still_skipped() -> None:
    found = fact_of(_event(_legacy("from-the-future")))
    assert found is None


# ---- the fold, and the prefix it shares with milestones


def test_facts_come_back_oldest_first_and_a_retire_removes_one(store: Store) -> None:
    first = _event(_legacy("rule", text="uno"), ts=CLOCK)
    second = _event(_legacy("rule", text="dos"), ts=CLOCK + 1)
    for event in (first, second):
        store.events.append(event)
    assert [f["text"] for f in facts(store)] == ["uno", "dos"]
    store.events.append(_event({"retires": first["id"]}, ts=CLOCK + 2))
    assert [f["text"] for f in facts(store)] == ["dos"]
    # And `log` still shows it, because an append-only log has no eraser.
    assert [f["text"] for f in facts(store, retired=True)] == ["uno", "dos"]


def test_a_prefix_still_names_a_fact_after_the_matcher_moved(store: Store) -> None:
    """`matching` now lives in `storage._prefix` and is shared with the milestone fold. It is
    re-exported from here because `usecases.context.retire` imports it from here, and the
    behaviour — exact hit wins, ambiguity is returned rather than resolved — is unchanged."""
    event = _event(_legacy("rule"))
    store.events.append(event)
    rows = facts(store)
    assert matching(rows, event["id"][:8]) == [event["id"]]
    assert matching(rows, event["id"]) == [event["id"]]
    assert matching(rows, "zzzzzzzz") == []
