"""The ephemeral channel, and the fan-out both channels are built on.

`Broadcast` is now the machinery under BOTH `BUS` (events, stored) and `WIRE` (narration
deltas, never stored), so these are the tests that keep one from breaking the other.
"""

from __future__ import annotations

from taskops.contracts import WireMessage
from taskops.engine import BUS, WIRE, Broadcast, is_wire


def _message(kind: str = "narration.delta", text: str = "hola",
             root: str = "/tmp/project") -> WireMessage:
    return WireMessage(kind=kind, label="2026-01-02", text=text, root=root)


def test_a_published_message_reaches_every_subscriber() -> None:
    channel: Broadcast[WireMessage] = Broadcast()
    one: list[WireMessage] = []
    two: list[WireMessage] = []
    channel.subscribe(one.append)
    channel.subscribe(two.append)
    channel.publish(_message())
    assert one == two == [_message()]


def test_cancelling_stops_delivery_and_is_idempotent() -> None:
    """The unsubscribe is the ONLY handle a caller has, and a live feed calls it from a
    `finally` that can run more than once — so a second call must not explode."""
    channel: Broadcast[WireMessage] = Broadcast()
    seen: list[WireMessage] = []
    cancel = channel.subscribe(seen.append)
    cancel()
    cancel()
    channel.publish(_message())
    assert seen == [] and len(channel) == 0


def test_a_listener_that_raises_does_not_stop_the_others() -> None:
    """THE reason publish swallows. A browser that vanished mid-narration must not be able to
    abort the model call that is publishing to it, nor starve the tab next to it."""
    channel: Broadcast[WireMessage] = Broadcast()
    seen: list[WireMessage] = []

    def explode(_message: WireMessage) -> None:
        raise RuntimeError("the socket went away")

    channel.subscribe(explode)
    channel.subscribe(seen.append)
    channel.publish(_message())
    assert seen == [_message()]


def test_the_wire_and_the_bus_are_different_channels() -> None:
    """The hard rule, executable: a narration delta must never travel with the events.

    `events.jsonl` is committed and its worth is that a human can read its diff. Publishing
    prose on the bus is the one mistake that would quietly destroy that, so a subscriber to
    one channel must never hear the other.
    """
    heard: list[object] = []
    cancel = BUS.subscribe(heard.append)
    try:
        WIRE.publish(_message())
    finally:
        cancel()
    assert heard == []


def test_a_wire_message_is_told_apart_from_an_event_by_its_shape() -> None:
    """Both are plain dicts down one generator, so this predicate is what routes them."""
    event = {"id": "e1", "task": "tk-1", "actor": "dev:berna", "kind": "comment",
             "body": {"text": "hi"}, "ts": 1.0}
    assert is_wire(_message()) is True
    assert is_wire(event) is False
    assert is_wire(None) is False
