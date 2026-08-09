"""The SHAPE of a server-scope call: what a host verb is handed, and what it is.

`admin.py` owns the registry and the gate; `grants.py` implements the verbs that
hand a credential out or take one back. Both need the same two names, and one
importing the other would be a cycle — so the shape lives here, below both, and
neither is the other's dependency. It is deliberately three declarations and no
behaviour: the moment a rule lands in this file, two modules are re-taking it.
"""

from __future__ import annotations

from typing import Any, Callable, NamedTuple

from .mounts import Mounts
from .._errors import BadRequest


class Call(NamedTuple):
    mounts: Mounts
    actor: str  # dev:<principal> — the credential's own subject, already proved
    role: str
    args: dict[str, Any]
    now: float


class Verb(NamedTuple):
    operation: str  # the `core/scope.py` operation that gates it
    need: str  # the capability the credential must carry: read | write
    run: Callable[[Call], dict[str, Any]]


def text(args: dict[str, Any], key: str) -> str:
    """A required argument, refused by NAME when it is missing or blank."""
    value = str(args.get(key, "")).strip()
    if not value:
        raise BadRequest(f"this call needs {key}=")
    return value
