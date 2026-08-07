"""Where a card stands with its reviewer — derived from the thread, never stored.

The same shape as `core/mentions.py`, for the same reason: "is this still
true?" is always answered by computing it, never by writing a second fact to
contradict the first later. A `submitted` event is the worker handing the card
in; a `reviewed` event is a verdict. Which verdict COUNTS is a fold:

    the last `submitted` opens a round; only a `reviewed` AFTER it answers it.

A verdict older than the latest submission is stale by construction — the
worker resubmitted, so the previous round is closed. Events are sorted by `ts`
with Python's STABLE sort and compared by POSITION, not by timestamp value:
a frozen or coarse clock makes an answer share the submission's timestamp, and
the round would survive its own verdict (`mentions.pending` and `replay` settle
simultaneity the same way — this had to agree with them).
"""

from __future__ import annotations

from typing import Mapping, NamedTuple

from .types import Event


class Standing(NamedTuple):
    """Where a card stands with its reviewer, folded from its thread."""

    submitted_at: float  # 0.0 = never submitted (or nothing since the last close)
    submitted_by: str  # who to talk back to
    verdict: str  # "" | "pass" | "changes" — since the last submission
    verdict_by: str
    note: str  # the reviewer's words, shown verbatim to the worker


EMPTY = Standing(0.0, "", "", "", "")

VERDICTS = ("pass", "changes")


def standing(events: list[Event]) -> Standing:
    """One card's thread → its Standing. EMPTY if it was never handed in."""
    ordered = sorted(events, key=lambda e: e["ts"])
    opened = -1
    for index, event in enumerate(ordered):
        if event["kind"] == "submitted":
            opened = index
    if opened < 0:
        return EMPTY
    handed = ordered[opened]
    verdict, verdict_by, note = "", "", ""
    for event in ordered[opened + 1 :]:
        if event["kind"] == "reviewed":
            verdict = str(event["body"].get("verdict", ""))
            verdict_by = event["actor"]
            note = str(event["body"].get("note", ""))
    return Standing(handed["ts"], handed["actor"], verdict, verdict_by, note)


def pending(threads: Mapping[str, list[Event]]) -> dict[str, Standing]:
    """task -> Standing, for every card that was ever handed in."""
    out: dict[str, Standing] = {}
    for task, events in threads.items():
        stood = standing(events)
        if stood.submitted_at:
            out[task] = stood
    return out
