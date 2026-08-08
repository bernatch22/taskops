"""What `report` folds per actor, over the report's WINDOW.

Hours were pinned in `test_verbs.py`; this file pins the two counts that ride
beside them — cards closed and commits — which exist so the Actors screen can
draw them without a second verb, a second pass or a stored figure.
"""

from __future__ import annotations

from typing import Any, Callable

import pytest

from taskops import verbs
from taskops.store.stores import Stores

BERNA = "dev:berna"
W1 = "agent:berna/w1"
W2 = "agent:berna/w2"

pytestmark = pytest.mark.usefixtures("clock")


def call(stores: Stores, verb: str, actor: str, **args: Any) -> dict[str, Any]:
    return verbs.call(stores, verb, actor, args)


def planned(stores: Stores) -> list[str]:
    out = call(
        stores,
        "plan",
        BERNA,
        milestone="MVP facturador",
        goal="read a bank CSV and issue invoices with VAT",
        tasks=[
            {"title": "invoice model", "files": ["src/models.py"]},
            {"title": "CSV parser", "files": ["src/parser.py"]},
            {"title": "VAT", "files": ["src/tax.py"]},
        ],
    )
    return [c["id"] for c in out["cards"]]


def worked(stores: Stores, clock: Callable[[float], None], actor: str, card: str, shas: list[str]) -> None:
    """Take a card, bind some commits to it, close it."""
    call(stores, "take", actor, task=card)
    for sha in shas:
        clock(60)
        call(
            stores, "bind", actor, task=card, sha=sha, subject=f"feat: {sha}",
            files=["src/models.py"],
        )
    clock(60)
    call(stores, "update", actor, task=card, status="done", comment="shipped")


def test_an_actor_shows_the_cards_it_closed_and_the_commits_it_made(
    stores: Stores, clock: Callable[[float], None]
) -> None:
    first, second, third = planned(stores)
    worked(stores, clock, W1, first, ["aaa1", "aaa2"])
    worked(stores, clock, W1, second, ["bbb1"])
    worked(stores, clock, W2, third, ["ccc1"])

    by_actor = call(stores, "report", BERNA, window="1d")["by_actor"]
    assert by_actor[W1]["closed"] == 2
    assert by_actor[W1]["commits"] == 3
    assert by_actor[W2]["closed"] == 1
    assert by_actor[W2]["commits"] == 1


def test_an_actor_who_committed_nothing_shows_zero_and_not_absent(
    stores: Stores, clock: Callable[[float], None]
) -> None:
    """A figure the board can compute is always drawn; only a board that cannot
    say omits the key, and that is the UI's `closed?`/`commits?`."""
    card = planned(stores)[0]
    call(stores, "take", W1, task=card)
    clock(600)
    call(stores, "update", W1, task=card, comment="halfway")

    entry = call(stores, "report", BERNA, window="1d")["by_actor"][W1]
    assert entry["closed"] == 0 and entry["commits"] == 0
    assert entry["seconds"] == 600.0


def test_the_counts_are_per_actor_and_the_board_wide_totals_do_not_move(
    stores: Stores, clock: Callable[[float], None]
) -> None:
    first, second, _ = planned(stores)
    worked(stores, clock, W1, first, ["aaa1", "aaa2"])
    worked(stores, clock, W2, second, ["bbb1"])

    out = call(stores, "report", BERNA, window="1d")
    assert out["total"]["closed"] == 2
    assert sum(a["closed"] for a in out["by_actor"].values()) == out["total"]["closed"]
    day = out["days"][-1]
    assert day["commits"] == 3  # board-wide, unchanged
    assert day["by_actor"][W1]["commits"] == 2 and day["by_actor"][W2]["commits"] == 1


def test_the_counts_are_over_the_window_and_nothing_older(
    stores: Stores, clock: Callable[[float], None]
) -> None:
    """`closed` and `commits` are window figures, not lifetime ones — work that
    fell out of the window is simply not there."""
    first, second, _ = planned(stores)
    worked(stores, clock, W1, first, ["aaa1"])
    clock(3 * 24 * 3600)
    worked(stores, clock, W1, second, ["bbb1", "bbb2"])

    entry = call(stores, "report", BERNA, window="1d")["by_actor"][W1]
    assert entry["closed"] == 1 and entry["commits"] == 2
    wide = call(stores, "report", BERNA, window="7d")["by_actor"][W1]
    assert wide["closed"] == 2 and wide["commits"] == 3
