"""store/ — the log is the truth, the cache is disposable, the leases are not."""

from __future__ import annotations

from pathlib import Path

from taskops.core import event as ev
from taskops.store import log
from tests.conftest import T0, card_event
from taskops.core.types import LEASE_TTL
from taskops.store.live import Live
from taskops.store.stores import Stores

# ── the log ─────────────────────────────────────────────────────────────────


def test_write_journals_before_it_indexes(stores: Stores) -> None:
    stores.write([card_event("tk-aaaaaa", T0)])
    lines = stores.log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert stores.cache.count() == 1


def test_the_same_event_twice_is_one_row(stores: Stores) -> None:
    event = card_event("tk-aaaaaa", T0)
    stores.write([event])
    stores.write([event])
    assert stores.cache.count() == 1
    assert len(stores.state()["cards"]) == 1


def test_a_tampered_line_is_quarantined_not_applied(tmp_path: Path) -> None:
    """v1 promised a verifiable log and verified nothing."""
    root = tmp_path / "board"
    root.mkdir()
    good = card_event("tk-aaaaaa", T0)
    forged = dict(good)
    forged["actor"] = "dev:mallory"  # id no longer matches the content
    path = root / "events.jsonl"
    path.write_text(ev.to_line(good) + "\n" + ev.to_line(forged) + "\n", encoding="utf-8")  # type: ignore[arg-type]

    events, rejected = log.read(path)
    assert len(events) == 1 and len(rejected) == 1
    assert "does not match" in rejected[0].reason

    board = Stores(root)
    assert board.cache.count() == 1
    assert path.with_suffix(".jsonl.quarantine").exists()
    board.close()


def test_a_blank_or_broken_line_does_not_stop_the_read(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(f"\n{{oops\n{ev.to_line(card_event('tk-aaaaaa', T0))}\n", encoding="utf-8")
    events, rejected = log.read(path)
    assert [e["task"] for e in events] == ["tk-aaaaaa"]
    assert len(rejected) == 1


# ── the cache is disposable ─────────────────────────────────────────────────


def test_deleting_the_cache_costs_nothing(tmp_path: Path) -> None:
    root = tmp_path / "board"
    first = Stores(root)
    first.write([card_event("tk-aaaaaa", T0), card_event("tk-bbbbbb", T0 + 1)])
    first.live.acquire("tk-aaaaaa", "agent:berna/w1", "tk-aaaaaa", T0)
    before = first.state()
    first.close()

    (root / "cache.sqlite").unlink()
    (root / "cache.sqlite-wal").unlink(missing_ok=True)

    second = Stores(root)
    assert second.state() == before
    assert second.live.holder("tk-aaaaaa", T0 + 1) == "agent:berna/w1"  # the claim survived
    second.close()


def test_state_is_incremental_after_the_first_fold(stores: Stores) -> None:
    stores.write([card_event("tk-aaaaaa", T0)])
    assert set(stores.state()["cards"]) == {"tk-aaaaaa"}
    stores.write([card_event("tk-bbbbbb", T0 + 1)])
    assert set(stores.state()["cards"]) == {"tk-aaaaaa", "tk-bbbbbb"}


def test_events_of_a_card_come_back_in_order(stores: Stores) -> None:
    stores.write(
        [
            card_event("tk-aaaaaa", T0),
            ev.make("tk-aaaaaa", "agent:berna/w1", "comment", {"text": "second"}, T0 + 5),
            ev.make("tk-aaaaaa", "agent:berna/w1", "comment", {"text": "third"}, T0 + 9),
        ]
    )
    assert [e["kind"] for e in stores.events("tk-aaaaaa")] == ["created", "comment", "comment"]


# ── leases: the mutex ───────────────────────────────────────────────────────


def test_two_workers_one_card_one_winner(tmp_path: Path) -> None:
    live = Live(tmp_path / "live.sqlite")
    first = live.acquire("tk-aaaaaa", "agent:berna/w1", "tk-aaaaaa", T0)
    second = live.acquire("tk-aaaaaa", "agent:berna/w2", "tk-aaaaaa", T0)
    assert first is not None and second is None
    assert live.holder("tk-aaaaaa", T0) == "agent:berna/w1"
    live.close()


def test_the_holder_re_taking_its_own_card_renews(tmp_path: Path) -> None:
    live = Live(tmp_path / "live.sqlite")
    first = live.acquire("tk-aaaaaa", "agent:berna/w1", "tk-aaaaaa", T0)
    again = live.acquire("tk-aaaaaa", "agent:berna/w1", "tk-aaaaaa", T0 + 60)
    assert first is not None and again is not None
    assert again["expires"] > first["expires"]
    live.close()


def test_an_expired_lease_is_takeable_and_shows_up_as_lapsed(tmp_path: Path) -> None:
    live = Live(tmp_path / "live.sqlite")
    live.acquire("tk-aaaaaa", "agent:berna/w1", "tk-aaaaaa", T0)
    later = T0 + LEASE_TTL + 1
    assert live.holder("tk-aaaaaa", later) is None
    assert [x["task"] for x in live.lapsed(later)] == ["tk-aaaaaa"]
    assert live.acquire("tk-aaaaaa", "agent:berna/w2", "tk-aaaaaa", later) is not None
    live.close()


def test_only_the_holder_releases(tmp_path: Path) -> None:
    """There is no force variant to test: a recover path was dead code and was
    deleted — an abandoned lease expires, it is never taken away."""
    live = Live(tmp_path / "live.sqlite")
    live.acquire("tk-aaaaaa", "agent:berna/w1", "tk-aaaaaa", T0)
    assert live.release("tk-aaaaaa", "agent:berna/w2") is False
    assert live.holder("tk-aaaaaa", T0) == "agent:berna/w1"
    assert live.release("tk-aaaaaa", "agent:berna/w1") is True
    assert live.holder("tk-aaaaaa", T0) is None
    live.close()


def test_any_call_renews_every_lease_that_actor_holds(tmp_path: Path) -> None:
    """The heartbeat IS the traffic — v1 used local-only activity events that
    never reached the server, so every remote worker looked dead after 60s."""
    live = Live(tmp_path / "live.sqlite")
    live.acquire("tk-aaaaaa", "agent:berna/w1", "tk-aaaaaa", T0)
    live.renew("agent:berna/w1", T0 + LEASE_TTL - 1)
    assert live.holder("tk-aaaaaa", T0 + LEASE_TTL + 1) == "agent:berna/w1"
    assert [a for a, _ in live.present(T0)] == ["agent:berna/w1"]
    live.close()
