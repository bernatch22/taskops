"""events.jsonl — THE truth. Everything else in this package is derived.

The append is part of the write path, not a follow-up: line, flush, fsync,
*then* the cache. v1 journalled after updating the database and four boards
ended up with a full cache and a 0-byte log.

Reading verifies every id against its content. A line that does not verify is
quarantined and returned to the caller, never applied — v1 promised a
verifiable log and checked no hashes at all.
"""

from __future__ import annotations

import os
from typing import Sequence, NamedTuple
from pathlib import Path

from .._errors import TaskopsError
from ..core.event import verify, to_line, from_line
from ..core.types import Event


class Rejected(NamedTuple):
    lineno: int
    reason: str
    raw: str


def append(path: Path, events: Sequence[Event]) -> None:
    """Append and fsync. Either the events are durable when this returns, or it raised."""
    if not events:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("a", encoding="utf-8") as handle:
            for event in events:
                handle.write(to_line(event) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as err:
        raise TaskopsError(f"cannot write the log at {path}: {err}") from err


def read(path: Path) -> tuple[list[Event], list[Rejected]]:
    """Every valid event, plus the lines that could not be trusted."""
    if not path.exists():
        return [], []
    events: list[Event] = []
    rejected: list[Rejected] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as err:
        raise TaskopsError(f"cannot read the log at {path}: {err}") from err
    for lineno, line in enumerate(text.splitlines(), start=1):
        raw = line.strip()
        if not raw:
            continue
        try:
            event = from_line(raw)
        except TaskopsError as err:
            rejected.append(Rejected(lineno, str(err), raw[:200]))
            continue
        if not verify(event):
            rejected.append(Rejected(lineno, "id does not match content", raw[:200]))
            continue
        events.append(event)
    return events, rejected


def quarantine(path: Path, rejected: Sequence[Rejected]) -> None:
    """Park untrusted lines next to the log so nothing is lost silently."""
    if not rejected:
        return
    target = path.with_suffix(path.suffix + ".quarantine")
    with target.open("a", encoding="utf-8") as handle:
        for item in rejected:
            handle.write(f"{path.name}:{item.lineno}\t{item.reason}\t{item.raw}\n")
