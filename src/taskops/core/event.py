"""Events: canonical form, content-addressed id, and the ONE coercion.

An event id is `sha256(canonical)[:32]`. That is what makes the log
idempotent: appending the same event twice is a no-op, replaying twice is
free, and two machines that observe the same fact produce the same id.

`verify()` is not decoration — v1's docs promised a verifiable log and never
checked a single hash. Here the reader quarantines a line whose id does not
match its content, so silent corruption is loud.
"""

from __future__ import annotations

import json
from typing import Any, cast

from .._ids import digest
from .types import KINDS, Event
from .._errors import BadRequest


def canonical(task: str, actor: str, kind: str, body: dict[str, Any], ts: float) -> str:
    """The exact bytes that are hashed. Stable key order, no spaces, 6-decimal ts."""
    try:
        payload = json.dumps(
            {"task": task, "actor": actor, "kind": kind, "body": body, "ts": round(ts, 6)},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as err:
        raise BadRequest(f"event body for {kind!r} is not JSON: {err}") from err
    return payload


def make(task: str, actor: str, kind: str, body: dict[str, Any], ts: float) -> Event:
    """Build a validated event. Unknown kinds are refused at the writer, not silently kept."""
    spec = KINDS.get(kind)
    if spec is None:
        raise BadRequest(f"unknown event kind {kind!r} — known: {', '.join(sorted(KINDS))}")
    missing = [k for k in spec.body_keys if k not in body]
    if missing:
        raise BadRequest(f"event {kind!r} needs body keys {missing}")
    if not task:
        raise BadRequest("an event always names a task (or 'project')")
    ts = round(ts, 6)
    return Event(
        id=digest(canonical(task, actor, kind, body, ts)),
        task=task,
        actor=actor,
        kind=kind,
        body=body,
        ts=ts,
    )


def verify(event: Event) -> bool:
    """Does the id match the content? Cheap, so the reader always asks."""
    expected = digest(
        canonical(event["task"], event["actor"], event["kind"], event["body"], event["ts"])
    )
    return expected == event["id"]


def to_line(event: Event) -> str:
    """One event, one line. The id is stored so a reader can verify it."""
    return json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def from_line(line: str) -> Event:
    """The ONE coercion from foreign JSON to an Event, for a caller holding TEXT
    (a log line). A caller holding the parsed object calls `of` directly."""
    try:
        raw: object = json.loads(line)
    except ValueError as err:
        raise BadRequest(f"not JSON: {err}") from err
    if not isinstance(raw, dict):
        raise BadRequest("an event line must be a JSON object")
    return of(cast("dict[str, Any]", raw))


def of(data: dict[str, Any]) -> Event:
    """The coercion proper: an already-parsed object becomes an Event, or raises.

    Strict about shape, lenient about extra body keys (an event written by a
    newer version keeps its data intact). v1 had fifteen input coercions
    scattered around and one of them read `claim="false"` as True.

    Split from `from_line` so the caller that receives events as OBJECTS rather
    than lines — `cli/pull.py`, paging a host's log down through the `events`
    verb — reaches the SAME coercion instead of re-serialising a dict just to
    have this function parse it back. One coercion, two doors.
    """
    for key in ("id", "task", "actor", "kind"):
        if not isinstance(data.get(key), str) or not data[key]:
            raise BadRequest(f"event field {key!r} must be a non-empty string")
    if not isinstance(data.get("ts"), (int, float)):
        raise BadRequest("event field 'ts' must be a number")
    raw_body: object = data.get("body", {})
    if not isinstance(raw_body, dict):
        raise BadRequest("event field 'body' must be an object")
    body = cast("dict[str, Any]", raw_body)
    return Event(
        id=data["id"],
        task=data["task"],
        actor=data["actor"],
        kind=data["kind"],
        body=body,
        ts=float(data["ts"]),
    )
