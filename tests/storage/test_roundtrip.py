"""Every entity survives the database, and its shape still matches its contract.

A TypedDict is erased at runtime, so `to_task` could quietly start returning a
string where a float belongs and nothing would complain until a renderer divided
by it. `assert_shape` is the check that a stored-then-loaded value still IS what
the contract says — run on what came back from real SQLite, not on a literal.
"""

from __future__ import annotations

from taskops._ids import event_id, new_task_id
from taskops.contracts import Event, Lease, Task
from taskops.storage import Store
from tests.conftest import CLOCK
from tests.contracts.shape import assert_shape


def a_task(**over: object) -> Task:
    base = Task(id=new_task_id(), title="Add the lease sweep", spec="Full brief.",
                status="backlog", priority=1, parent=None, labels=["storage"],
                files=["src/taskops/storage/_leases.py"], created_by="dev:berna", assignee="", reviewer="",
                created=CLOCK, updated=CLOCK)
    return Task(**{**base, **over})          # type: ignore[typeddict-item]


def test_a_task_round_trips_and_matches_its_contract(store: Store) -> None:
    written = a_task()
    store.tasks.insert(written)
    read = store.tasks.need(written["id"])
    assert_shape(read, Task)
    assert read == written


def test_json_columns_survive_as_lists(store: Store) -> None:
    """`labels` and `files` are JSON text in SQLite and lists everywhere else.

    The conversion is the kind that works until a value is empty or holds a
    character somebody quoted, so both ends are checked here rather than trusted.
    """
    written = a_task(labels=[], files=["a/b c.py", 'weird"name.py'])
    store.tasks.insert(written)
    read = store.tasks.need(written["id"])
    assert read["labels"] == []
    assert read["files"] == ["a/b c.py", 'weird"name.py']


def test_a_lease_round_trips(store: Store) -> None:
    task = a_task()
    store.tasks.insert(task)
    lease = Lease(task=task["id"], actor="agent:berna/one", session="sess-1",
                  branch="", acquired=CLOCK, expires=CLOCK + 900)
    assert store.leases.acquire(lease) is True
    read = store.leases.get(task["id"])
    assert read is not None
    assert_shape(read, Lease)
    assert read == lease


def test_an_event_round_trips_with_its_body(store: Store) -> None:
    """The body is an open dict, so the test uses a NESTED one.

    Flat payloads would pass even if the column stored `str(dict)` instead of JSON.
    """
    body = {"sha": "abc123", "files": ["x.py"], "stats": {"added": 3}}
    event = Event(id=event_id(task="tk-1", actor="dev:berna", kind="commit",
                              body=body, ts=CLOCK),
                  task="tk-1", actor="dev:berna", kind="commit", body=body, ts=CLOCK)
    assert store.events.append(event) is True
    read = store.events.of_task("tk-1")
    assert len(read) == 1
    assert_shape(read[0], Event)
    assert read[0]["body"] == body


def test_appending_the_same_event_twice_is_a_no_op(store: Store) -> None:
    """The property the whole replication story rests on.

    The id is the content hashed, so an event arriving from a `git pull` and from
    the relay is ONE row — not a duplicate comment in somebody's inbox.
    """
    event = Event(id=event_id(task="tk-1", actor="dev:berna", kind="comment",
                              body={"text": "hi"}, ts=CLOCK),
                  task="tk-1", actor="dev:berna", kind="comment",
                  body={"text": "hi"}, ts=CLOCK)
    assert store.events.append(event) is True
    assert store.events.append(event) is False
    assert len(store.events.of_task("tk-1")) == 1


def test_a_malformed_json_column_degrades_instead_of_raising(store: Store) -> None:
    """A row another taskops wrote must never make the board unreadable.

    Written through the SQL layer directly because no API can produce this — which
    is the point: the value comes from a file git merged, not from this process.
    """
    task = a_task()
    store.tasks.insert(task)
    store.db.execute("UPDATE tasks SET labels='{not json' WHERE id=?", (task["id"],))
    read = store.tasks.need(task["id"])
    assert read["labels"] == []
