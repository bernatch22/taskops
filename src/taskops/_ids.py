"""Identifiers.

Two shapes, both deliberate:

* a card id is **random** (`tk-` + 6 hex). It is a name, not a hash: it must
  stay stable while the card is edited, and it is what the git branch and the
  commit trailer are made of.
* an event id is the **sha256 of its canonical form, 32 hex**. Content-hash
  ids are what make the log idempotent (`INSERT OR IGNORE` and replaying twice
  is free). v1 truncated to 16 hex — 64 bits — and a collision there is a
  silently dropped event, so 128 bits it is.
"""

from __future__ import annotations

import secrets
from hashlib import sha256

TASK_PREFIX = "tk-"
MILESTONE_PREFIX = "ms-"
EVENT_ID_LEN = 32


def new_task_id() -> str:
    """`tk-` + 6 random hex. Collision-checked by the caller's INSERT."""
    return TASK_PREFIX + secrets.token_hex(3)


def new_milestone_id() -> str:
    return MILESTONE_PREFIX + secrets.token_hex(3)


def is_task_id(value: str) -> bool:
    return _is(value, TASK_PREFIX)


def is_milestone_id(value: str) -> bool:
    return _is(value, MILESTONE_PREFIX)


def _is(value: str, prefix: str) -> bool:
    body = value[len(prefix) :]
    return (
        value.startswith(prefix) and len(body) == 6 and all(c in "0123456789abcdef" for c in body)
    )


def digest(canonical: str) -> str:
    """sha256 of an already-canonical string, truncated to 128 bits."""
    return sha256(canonical.encode("utf-8")).hexdigest()[:EVENT_ID_LEN]


def new_token() -> str:
    """A credential or invite secret. Only the sha256 of this is ever stored."""
    return secrets.token_urlsafe(24)
