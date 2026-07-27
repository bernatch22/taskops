"""Layer 0 — how a task and an event get their names.

Two different jobs, and the difference is the whole design:

**Task ids are RANDOM** (`tk-4f2a9c`). Many machines create tasks without
talking to each other, so an id must be collision-free without coordination —
which rules out a counter. Random also means unguessable, so a task id in a
branch name leaks no ordering information about the project.

**Event ids are the CONTENT, hashed.** The event log is replicated by `git pull`
and by the relay, and the same event can arrive by both paths: with a content
hash, importing it twice is a primary-key no-op instead of a duplicate comment
in somebody's inbox. It also makes the log verifiable — an event whose id does
not match its content was edited after the fact.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any

__all__ = ["new_task_id", "event_id", "slugify", "TASK_PREFIX"]

TASK_PREFIX = "tk-"
_TASK_BYTES = 3  # 6 hex chars: 16.7M ids, and the whole id fits a branch name
_EVENT_CHARS = 16


def new_task_id() -> str:
    """A fresh task id. Uniqueness is checked at INSERT, not assumed here."""
    return TASK_PREFIX + secrets.token_hex(_TASK_BYTES)


def event_id(*, task: str, actor: str, kind: str, body: dict[str, Any], ts: float) -> str:
    """The id of an event, derived from everything the event says.

    `sort_keys` and a fixed float format matter more than they look: two
    machines must hash the same event to the same id, and Python's dict order
    and `repr(float)` are not a contract across versions.
    """
    payload = json.dumps(
        {"task": task, "actor": actor, "kind": kind, "body": body, "ts": f"{ts:.6f}"},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:_EVENT_CHARS]


def slugify(text: str, *, limit: int = 32) -> str:
    """A title -> the branch-safe half of `tk/<id>/<slug>`.

    Deliberately lossy and never parsed back: the id is what identifies the
    task, so this only has to be readable in a `git branch` listing. Everything
    git or a shell would treat as special becomes a dash.
    """
    kept = [c.lower() if c.isalnum() else "-" for c in text.strip()]
    slug = "".join(kept).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:limit].strip("-") or "task"
