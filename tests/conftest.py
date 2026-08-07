"""Shared fixtures: a real board on disk, and a clock that does not move."""

from __future__ import annotations

from typing import Any, Callable, Iterator
from pathlib import Path

import pytest

from taskops import _clock
from taskops.core import event as ev
from taskops.core.types import Event
from taskops.store.stores import Stores

T0 = 1_770_000_000.0  # a fixed Thursday; every test that needs "now" starts here


@pytest.fixture()
def clock() -> Iterator[Callable[[float], None]]:
    """Freeze time. Tests advance it explicitly; nothing else reads the wall clock."""
    _clock.set_now(T0)

    def advance(seconds: float) -> None:
        _clock.set_now(_clock.now() + seconds)

    yield advance
    _clock.set_now(None)


@pytest.fixture()
def stores(tmp_path: Path) -> Iterator[Stores]:
    board = Stores(tmp_path / "board")
    yield board
    board.close()


def card_event(ident: str, ts: float, **over: Any) -> Event:
    body: dict[str, Any] = {
        "id": ident,
        "title": ident,
        "spec": "",
        "status": "open",
        "priority": 2,
        "milestone": "ms-1",
        "after": [],
        "files": [],
        "created_by": "dev:berna",
    }
    body.update(over)
    return ev.make(ident, "dev:berna", "created", {"card": body}, ts)
