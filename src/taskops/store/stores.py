"""`Stores` — the three files of a board, and the one write path through them.

    <board>/events.jsonl   the truth        (append + fsync FIRST)
    <board>/cache.sqlite   derived          (discardable)
    <board>/live.sqlite    leases, presence (never discardable)

Every verb receives a `Stores` and nothing else that touches disk. The write
order is not negotiable: journal, then index, then state. A crash between the
first and the second costs a rebuild, which is automatic; the other order
costs the events themselves.
"""

from __future__ import annotations

import threading
from typing import Sequence
from pathlib import Path

from . import log
from .live import Live
from ..core import replay
from .cache import Cache
from ..core.types import Event
from ..core.replay import State

LOG_NAME = "events.jsonl"


class Stores:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.log_path = root / LOG_NAME
        self.cache = Cache(root / "cache.sqlite")
        self.live = Live(root / "live.sqlite")
        self._lock = threading.RLock()
        self._state: State | None = None
        self._head = 0
        self.rejected: list[log.Rejected] = []
        self._bootstrap()

    def write(self, events: Sequence[Event]) -> int:
        """Journal, index, fold. Returns the board's sequence after the write."""
        if not events:
            return self.head()
        with self._lock:
            log.append(self.log_path, events)
            seq = self.cache.add(events)
            if self._state is not None:
                replay.fold(list(events), self._state)
                self._head = seq
            return seq

    def state(self) -> State:
        """The folded board. Cold: replay everything. Warm: apply what is new."""
        with self._lock:
            if self._state is None:
                rows = self.cache.since(0)
                self._state = replay.fold([e for _, e in rows])
                self._head = rows[-1][0] if rows else 0
                return self._state
            fresh = self.cache.since(self._head)
            if fresh:
                replay.fold([e for _, e in fresh], self._state)
                self._head = fresh[-1][0]
            return self._state

    def head(self) -> int:
        return self.cache.head()

    def ids(self) -> set[str]:
        return self.cache.ids()

    def kinds(self) -> dict[str, int]:
        return self.cache.kinds()

    def events(self, task: str) -> list[Event]:
        return self.cache.by_task(task)

    def threads(self) -> dict[str, list[Event]]:
        """Every event, grouped by card, in ARRIVAL order — the whole log, once.

        What is unanswered can only be read off the threads themselves, so this
        is the read `core/mentions.py` folds. It is the same single pass
        `state()` already makes, and deliberately not an index: an index of
        "still pending" would be a stored answer to a derived question.
        """
        grouped: dict[str, list[Event]] = {}
        for _, event in self.cache.since(0):
            grouped.setdefault(event["task"], []).append(event)
        return grouped

    def rebuild(self) -> int:
        """Throw the cache away and replay the log. The leases do not notice."""
        with self._lock:
            events, rejected = log.read(self.log_path)
            self.rejected = rejected
            log.quarantine(self.log_path, rejected)
            self.cache.add(events)
            self._state = None
            self._head = 0
            return self.head()

    def close(self) -> None:
        self.cache.close()
        self.live.close()

    def _bootstrap(self) -> None:
        """A fresh (or deleted) cache reconstructs itself from the log, silently."""
        if self.cache.count() == 0 and self.log_path.exists():
            self.rebuild()
