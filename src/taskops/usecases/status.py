"""`taskops status` — the one read somebody makes before they start working.

git's `status` is the model: what is mine, what changed, what have I not sent. The
value is that it is CHEAP — one SQLite file, no git subprocess, no network — because a
command people run every few minutes has to cost nothing or they stop running it. The
only exception is `fetch=True`, which is a `pull` the caller asked for by name.

Everything here comes from projections that already exist. `engine.board` gives every
card with its lease and its dependency counts in two queries, so the bottleneck, the
claims and the counts are one pass over a list rather than a query per card — the same
reason the board itself is built that way.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from .._clock import now
from .._types import OPEN_STATUSES
from ..contracts import Card, ReportEntry
from ..contracts.status import Bottleneck, Claim, Reports, Status, Sync
from ..engine import board, date_of, shift
from ..engine.day import window
from ..storage import Store
from ._project import caller, project
from ._statusfacts import objective_of
from .index import report_index
from .remote import read_remote, remote_path

__all__ = ["status", "IDLE_DAYS", "EXPIRING"]

IDLE_DAYS = 7
"""How long an open card may sit untouched before status counts it as forgotten.

A week rather than a day: a backlog is allowed to be a backlog. What this catches is the
card somebody claimed on Monday, half-did, and has not opened since — the failure mode a
board full of green columns hides.
"""

EXPIRING = 300.0
"""Seconds of lease left below which a claim is shown as expiring, in every renderer.

Decided here and not in `render/` on purpose: two renderers free to pick their own
threshold would eventually disagree about which claims are in trouble, and the one on
the screen somebody is looking at would be the wrong one.
"""


def status(start: Path | str, *, actor: str = "", fetch: bool = False,
           idle_days: int = IDLE_DAYS) -> Status:
    """Where the project stands. Touches the network only when `fetch` is passed."""
    if fetch:
        from .pushpull import pull  # lazy: the ONE path out of this module

        pull(start)
    entries = report_index(start)
    with project(start) as store:
        return _snapshot(store, actor or caller(store)["id"], entries, idle_days)


def _snapshot(store: Store, me: str, entries: list[ReportEntry], idle_days: int) -> Status:
    at = now()
    snap = board(store)
    cards = [card for column in snap["columns"] for card in column["cards"]]
    living = [card for card in cards if card["task"]["status"] in OPEN_STATUSES]
    held = [card for card in cards if card["lease"]]
    return Status(
        project=store.root.name, root=str(store.root), actor=me,
        objective=objective_of(store), total=snap["total"], ready=snap["ready"],
        blocked=sum(1 for c in living if c["task"]["status"] == "blocked"),
        counts={col["status"]: len(col["cards"]) for col in snap["columns"]},
        mine=[_claim(c, at) for c in held if _actor_of(c) == me],
        others=[_claim(c, at) for c in held if _actor_of(c) != me],
        idle=sum(1 for c in living if at - c["task"]["updated"] > idle_days * 86400.0),
        idle_days=idle_days, bottleneck=_bottleneck(living),
        reports=_reports(store, entries, at), sync=_sync(store))


def _actor_of(card: Card) -> str:
    return card["lease"]["actor"] if card["lease"] else ""


def _claim(card: Card, at: float) -> Claim:
    left = (card["lease"]["expires"] - at) if card["lease"] else 0.0
    return Claim(actor=_actor_of(card), task=card["task"]["id"],
                 title=card["task"]["title"], state=card["task"]["status"],
                 left=left, expiring=left < EXPIRING)


def _bottleneck(living: list[Card]) -> Bottleneck | None:
    """The open card the most others wait on. None when nothing blocks anything.

    Ties go to whichever comes first in board order, which is status order — a card
    already in flight beats an identical one still in the backlog, and that is the
    right advice anyway.
    """
    ranked = [card for card in living if card["blocks"]]
    best = max(ranked, key=lambda card: card["blocks"]) if ranked else None
    return None if best is None else Bottleneck(
        task=best["task"]["id"], title=best["task"]["title"], blocks=best["blocks"])


def _reports(store: Store, entries: list[ReportEntry], at: float) -> Reports:
    """Today's volume and whether yesterday was written up.

    Yesterday and not today, because today's report is not late yet — the question
    status answers is whether the habit slipped, and it slips one day at a time.
    """
    today, seen = date_of(at), {entry["label"]: entry for entry in entries}
    yesterday, (start, end) = shift(today, days=-1), window(today)
    written = seen.get(yesterday)
    return Reports(today=today, yesterday=yesterday,
                   today_events=sum(1 for e in store.events.since(start - 1.0)
                                    if start <= e["ts"] < end),
                   yesterday_written=bool(written and written["exists"]),
                   yesterday_narrated=bool(written and written["has_narration"]))


def _sync(store: Store) -> Sync:
    """How far ahead of the server this machine is, and when it last spoke to it.

    `last_sync` is the mtime of `remote.json`, which is where both cursors are saved:
    a timestamp nobody records is a timestamp nobody can forget to record, and the file
    is written by every push and every pull by construction.
    """
    remote = read_remote(store.root)
    if remote is None:
        return Sync(host="", ahead=0, last_sync=0.0)
    path = remote_path(store.root)
    return Sync(host=urlparse(remote["url"]).netloc,
                ahead=max(0, store.events.max_seq() - remote["pushed"]),
                last_sync=path.stat().st_mtime if path.exists() else 0.0)
