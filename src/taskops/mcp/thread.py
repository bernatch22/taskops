"""The conversation about a card: every event, oldest first, never cut.

One line per event that says the thing that CHANGED, not just the name of the
kind — "edited: files → [src/tax.py]" is a fact; "edited" is noise.
"""

from __future__ import annotations

from typing import Any

from . import render
from .._json import as_rows, as_object


def lines(rows: object, now: float) -> list[str]:
    out: list[str] = []
    for event in as_rows(rows):
        body = as_object(event.get("body"))
        when = render.ago(now - float(event.get("ts", now)))
        out.append(
            f"- {when} · {event.get('actor')} · {event.get('kind')}"
            f"{detail(str(event.get('kind')), body)}".rstrip()
        )
    return out or ["- (nothing yet)"]


def detail(kind: str, body: dict[str, Any]) -> str:
    """One line per event, saying the thing that changed — not just its name."""
    if kind == "created":
        return f": {as_object(body.get('card')).get('title', '')}"
    if kind == "edited":
        return f": {body.get('field')} → {body.get('to')}"
    if kind == "status":
        reason = body.get("reason") or body.get("note") or ""
        no_code = " (no code)" if body.get("no_code") else ""
        return f": {body.get('to')}{no_code}" + (f" — {reason}" if reason else "")
    for key in ("text", "note", "to", "subject", "into"):
        if body.get(key):
            return f": {body[key]}"
    return ""
