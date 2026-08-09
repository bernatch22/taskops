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
    """A credential or invite secret. Only the sha256 of this is ever stored.

    **Never starts with `-`.** `token_urlsafe` draws from `A-Za-z0-9_-`, so
    roughly one token in 64 begins with a hyphen — and every one of those is a
    token that cannot be passed to the CLI: `taskops join x --invite -Ab9…`
    makes argparse read the secret as an option and refuse with *expected one
    argument*. It fails for the user who was unlucky, on a value they cannot
    influence, with a message about the flag rather than the value.

    Fixed HERE, at the one place a secret is minted, rather than by quoting or
    `--invite=` at each call site: the token also travels in URLs, briefs and
    shell snippets nobody controls. Found by CI — the runner drew a leading
    hyphen on the first run this suite ever had off this laptop.

    Rerolling (not stripping) keeps every token the full 24 bytes of entropy."""
    while (token := secrets.token_urlsafe(24)).startswith("-"):
        pass
    return token
