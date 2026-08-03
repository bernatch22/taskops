"""The project settings: written validated, read from the log, never from a file.

What the mechanism it replaced could not do is what most of this file is about. A `reviewer:`
prefix inside a free-text decision could not refuse a typo, so it degraded to "nobody named"
and every card came out unreviewed in silence. Each refusal below is that failure, closed.

The last test is the one that matters architecturally and it is a SEAM: a setting that lives
only in `db.sqlite` is a setting a clone disagrees about and `rm db.sqlite` destroys. It walks
the value through the committed log and a rebuilt cache, which is the only way to prove the
policy is derived from the log rather than stored beside it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taskops import BadRequest
from taskops._types import EVENT_KINDS, PEER
from taskops.contracts.policy import NAMES, POLICY_KIND
from taskops.storage import Store, all_events
from taskops.usecases import init, plan, policy_show, rebuild, set_policy, sync
from taskops.usecases.milestone import open_chapter
from taskops.usecases.policy import _VALIDATORS
from tests.usecases.test_agents import COLLECTORS, write_agent


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A project that has ONE registered specialist, `taskops-collectors`."""
    # Every card belongs to a chapter: the fixture opens one so the test can be about its own
    # subject rather than about that.
    init(tmp_path, install_git_hooks=False)
    open_chapter(tmp_path, "the chapter these tests plan into",
                 actor="dev:berna")
    write_agent(tmp_path, "taskops-collectors", COLLECTORS)
    return tmp_path


def reviewer_of(project: Path, **entry: object) -> str:
    return plan(project, [{"title": "t", **entry}])["created"][0]["reviewer"]


# ---- writing one


def test_a_setting_reads_back_as_it_was_written(project: Path) -> None:
    set_policy(project, "reviewer", PEER, actor="dev:ana")
    assert [(p["name"], p["value"]) for p in policy_show(project)] == [("reviewer", PEER)]


def test_the_last_write_wins_and_the_earlier_one_stays_in_the_log(project: Path) -> None:
    """No retire verb, on purpose: setting it back is stating the new value. The history is
    the log's job, and it keeps it — which is what makes "who turned this off" answerable."""
    set_policy(project, "reviewer", PEER, actor="dev:ana")
    set_policy(project, "reviewer", "human", actor="dev:uno")

    assert [p["value"] for p in policy_show(project)] == ["human"]
    sync(project)
    written = [e["body"]["value"] for e in all_events(project) if e["kind"] == POLICY_KIND]
    assert written == [PEER, "human"], "both values are in the log, in order"


def test_clearing_it_is_a_value_and_not_an_absence(project: Path) -> None:
    """"Explicitly no default" is a state somebody chose, and it has to be distinguishable
    from never having chosen — otherwise turning a policy off cannot be reviewed later."""
    set_policy(project, "reviewer", PEER, actor="dev:ana")
    assert set_policy(project, "reviewer", "none", actor="dev:ana")["value"] == ""
    assert reviewer_of(project) == ""


# ---- the refusals, which are the entire reason this is not a decision


def test_a_value_that_names_no_specialist_is_refused_at_the_door(project: Path) -> None:
    """The failure that motivated the move. As a decision this recorded happily, matched no
    specialist at read time, and silently made every card unreviewed."""
    with pytest.raises(BadRequest) as caught:
        set_policy(project, "reviewer", "taskops-collectrs", actor="dev:ana")
    assert "taskops-collectors" in str(caught.value)
    assert policy_show(project) == [], "nothing was written"


def test_a_setting_this_version_does_not_know_is_refused_naming_the_ones_it_has(
        project: Path) -> None:
    with pytest.raises(BadRequest) as caught:
        set_policy(project, "revewer", PEER, actor="dev:ana")
    assert "reviewer" in str(caught.value)


def test_every_name_has_a_validator() -> None:
    """The lookup IS the registration: a name with no validator is a setting nothing checks,
    which is the state this whole module exists to leave behind. Adding a `Name` without a
    row here would restore it silently, so the two lists are asserted to agree."""
    assert set(NAMES) == set(_VALIDATORS)


def test_the_kind_is_declared_where_every_reader_looks() -> None:
    """A kind absent from `EVENT_KINDS` is legal to the type checker and unknown to the MCP
    schema and the board's filter, both of which iterate the tuple."""
    assert POLICY_KIND in EVENT_KINDS


# ---- forward compatibility, the same contract the event reader keeps


def test_a_setting_from_a_newer_taskops_is_skipped_and_not_fatal(project: Path) -> None:
    """A teammate on a newer version WILL write settings this one has never heard of into the
    shared log. Refusing to read the project because of one is the failure mode; skipping is
    what every other reader here does."""
    from taskops.engine import record

    with Store(project) as store:
        record(store, task="project", actor="dev:ana", kind=POLICY_KIND,
               body={"name": "from-the-future", "value": "whatever"})
    assert policy_show(project) == []


# ---- the seam: the log is truth, the cache is disposable


def test_the_setting_survives_the_cache_being_deleted(project: Path) -> None:
    """Where a config file would have lost it, and the failure this project has already paid
    for once: four server boards held a full database and a 0-byte log, and `rm db.sqlite` —
    the documented repair for a cache — would have destroyed every one of them.

    Exported, cache deleted, rebuilt from the file alone. If the policy were stored rather than
    derived, the value comes back empty and the card after it names nobody.
    """
    set_policy(project, "reviewer", PEER, actor="dev:ana")
    sync(project)                                # export: the event reaches events.jsonl

    (project / ".taskops" / "db.sqlite").unlink()
    rebuild(project)

    assert [p["value"] for p in policy_show(project)] == [PEER]
    assert reviewer_of(project) == PEER, "and a card created after the rebuild still gets it"
