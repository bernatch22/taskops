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


@pytest.fixture(autouse=True)
def _identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """WHO the suite is, pinned — the same argument as the frozen clock, and as
    `virgin`'s fixture HOME, applied to the last ambient input left.

    A principal is guessed from `$USER` when no `--as` is given
    (`cli/commands.py::principal`), and the fixtures that bootstrap a host
    register `berna` as its owner. On a machine whose unix user IS berna every
    push signs in and passes; anywhere else — a CI runner, a colleague's laptop
    — the same code signs in as `runner` and the host correctly refuses a
    principal it never registered. Nine push tests were green here and red on
    the first CI run for exactly that reason, and the failure blamed
    `session.mint` rather than the environment.

    Pinned in conftest and not in one fixture because the guess is read at CALL
    time by whichever command the test drives, not at setup by the fixture that
    created the owner."""
    monkeypatch.setenv("USER", "berna")


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
