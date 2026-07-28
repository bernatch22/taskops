"""Reading what a taskops server sent back — three functions and no I/O.

Split out of `_wireclient` when the login calls arrived and the module hit its budget. The
line is not arbitrary: everything here answers "what did those bytes mean", nothing here
knows there is a network, and that is exactly what makes each one testable from a literal.
"""

from __future__ import annotations

import json
from typing import Any, cast

__all__ = ["decode", "failure", "cause"]


def decode(raw: bytes) -> dict[str, Any]:
    """A JSON object, or an empty one. A body that is not JSON is not a crash: an nginx in
    front of the server answers 502 in HTML, and the reader wants the status, not a
    traceback through the parser."""
    try:
        parsed: Any = json.loads(raw.decode("utf-8", errors="replace") or "{}")
    except json.JSONDecodeError:
        return {}
    return cast("dict[str, Any]", parsed) if isinstance(parsed, dict) else {}


def failure(payload: dict[str, Any], where: str, code: int) -> str:
    """The server's own `error` field, verbatim. It was written for a person; replacing it
    with "HTTP 409" throws away the only text that says what to do."""
    told = str(payload.get("error") or "").strip()
    return told or f"{where} answered {code} and said nothing a person can act on"


def cause(err: Exception) -> str:
    return str(getattr(err, "reason", "") or err) or err.__class__.__name__
