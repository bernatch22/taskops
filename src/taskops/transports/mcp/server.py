"""The stdio loop: one JSON object per line in, one response per line out.

Everything protocol-shaped happens in `protocol`; what is left here is the wire. Written
against two streams rather than sys.stdin/sys.stdout directly, so the loop's real behaviour
— a malformed line, a notification, the order of replies — is testable without a subprocess.
"""

from __future__ import annotations

import json
import sys
from typing import IO, Any, cast

from .protocol import respond

__all__ = ["serve", "main"]


def serve(reader: IO[str], writer: IO[str]) -> None:
    """Answer messages until the input ends.

    A line that is not a JSON object is SKIPPED, not fatal: a host that writes one piece of
    garbage should not lose the rest of the session, and there is no id to answer it with
    anyway.
    """
    for raw in reader:
        line = raw.strip()
        if not line:
            continue
        message = _parse(line)
        reply = respond(message) if message is not None else None
        if reply is not None:
            writer.write(json.dumps(reply) + "\n")
            writer.flush()


def _parse(line: str) -> dict[str, Any] | None:
    try:
        message: object = json.loads(line)
    except json.JSONDecodeError:
        return None
    return cast("dict[str, Any]", message) if isinstance(message, dict) else None


def main() -> int:
    """`python -m taskops.transports.mcp`, and what a host registers:
    `claude mcp add taskops -- python3 -m taskops.transports.mcp`."""
    serve(sys.stdin, sys.stdout)
    return 0
