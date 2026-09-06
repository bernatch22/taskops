"""One thread per WATCHED worktree: scan it, publish when it moved — and hold
the last scan for the listing door while the thread runs.

`watcher.py`'s shape, applied to a directory instead of a board: started when
somebody is listening on the Editor's feed for that tree, gone once nobody is,
and what it publishes is a SIGNAL — `{"type": "change", "tree", "seq"}` — never
the files. The page answers a signal by re-reading the listing through the
door, where the credential applies again, and compares mtimes to decide which
open tab to re-read. A dropped or doubled signal therefore costs a listing and
nothing else (`feed.py`'s rule, unchanged).

WHY THE CACHE IS HERE. A scan is three git calls and a stat per file
(`gitwork/scan.py`); the watcher already pays that once a second for a tree
somebody is looking at, so a listing request on that tree is served the
watcher's last reading — at most a tick old — rather than a fourth walk. A tree
nobody watches is scanned on the request, because there is no reading to hand
out. No clock decides freshness: the watched/unwatched fact does, which is what
keeps this correct under the frozen clock the test suite runs on.

The instance lives on `BoardServer`, one per process, so two servers in one
test cannot share a scan — the same reason `Mounts` owns `_watched`.
"""

from __future__ import annotations

from time import sleep
from typing import NamedTuple
from pathlib import Path
from threading import Lock, Thread

from . import feed
from .._errors import TaskopsError
from ..gitwork import scan

WATCH_SECONDS = 1.0
"""A change on disk reaches the page within a tick plus a listing. A worker
saves a file, the page shows it — that is the whole feature, and one second is
under the time it takes to look from the terminal to the browser."""


class Held(NamedTuple):
    scan: scan.Scan
    seq: int  # bumps when the scan differs from the one before it


class Trees:
    def __init__(self, hub: feed.Hub) -> None:
        self.hub = hub
        self._lock = Lock()
        self._held: dict[str, Held] = {}
        self._watched: set[str] = set()

    @staticmethod
    def key(board: str, name: str) -> str:
        """The hub's key AND the cache's — one string, so a listener and a scan
        cannot disagree about which tree they name. A board name carries no
        slash (`mounts.NAME`), so it cannot collide with a board's own feed."""
        return f"{board}/editor/{name}"

    def listing(self, key: str, tree: Path, base: str = "") -> Held:
        """The watcher's reading when one runs, a fresh scan otherwise. `base`
        is the sha the branch's own changes are read against (`scan.take`)."""
        with self._lock:
            held = self._held.get(key) if key in self._watched else None
        return held if held is not None else self._refresh(key, tree, base)

    def watch(self, key: str, tree: Path, name: str, base: str = "") -> None:
        """Watch `tree`, once. A second listener joins the thread already running.

        The BASELINE is taken here, on the request thread, before the caller
        sends `hello`: a file written the moment the page saw the stream open
        must read as a change against what stood before, not fold into a first
        scan racing it on another thread (which is exactly what happened)."""
        with self._lock:
            if key in self._watched:
                return
            self._watched.add(key)
        self._refresh(key, tree, base)
        Thread(target=self._pump, args=(key, tree, name, base), daemon=True).start()

    def _refresh(self, key: str, tree: Path, base: str) -> Held:
        taken = scan.take(tree, base=base)
        with self._lock:
            before = self._held.get(key)
            moved = before is None or scan.differs(before.scan, taken)
            fresh = Held(taken, (before.seq if before else 0) + (1 if moved else 0))
            self._held[key] = fresh
        return fresh

    def _pump(self, key: str, tree: Path, name: str, base: str) -> None:
        try:
            seen = self._held[key].seq
            while True:
                # Sleep BEFORE asking whether anybody listens — `watch` runs on
                # the way into `feed.attach`, which is what subscribes.
                sleep(WATCH_SECONDS)
                if not self.hub.count(key):
                    return
                held = self._refresh(key, tree, base)
                if held.seq != seen:
                    seen = held.seq
                    self.hub.publish(key, {"type": "change", "tree": name, "seq": held.seq})
        except (TaskopsError, OSError):
            return  # a tree that went away is not worth a traceback per second
        finally:
            with self._lock:
                self._watched.discard(key)
