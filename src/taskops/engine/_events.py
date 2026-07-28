"""The `stream-json` wire format, read. Pure: a line in, a fragment out, no process in sight.

Split from `_stream` so the shape of the CLI's events can be tested from string literals, which
is the only way to pin the one trap in them.

Every stdout line of `claude --output-format stream-json --include-partial-messages` is one JSON
object. Visible text arrives as
`{"type": "stream_event", "event": {"delta": {"type": "text_delta", "text": "…"}}}` — but the
THINKING deltas arrive FIRST and carry `"text": None`, so a reader that takes `delta["text"]`
because the key is there yields `None` and crashes on the first join. Filter on the delta's TYPE.
"""

from __future__ import annotations

import json
from typing import Any, cast

from .._errors import NarrationFailed

__all__ = ["parsed", "text_delta", "check_result"]


def parsed(line: str) -> dict[str, Any]:
    """One stdout line as an object, or `{}`.

    A line that is not JSON is skipped rather than fatal: the CLI prints the odd warning on
    stdout, and throwing away a finished narration over one of them would be absurd.
    """
    try:
        loaded: object = json.loads(line)
    except json.JSONDecodeError:
        return {}
    return cast("dict[str, Any]", loaded) if isinstance(loaded, dict) else {}


def text_delta(event: dict[str, Any]) -> str:
    """The visible text of a partial message, or "" for anything else — including a thinking
    delta, whose `text` is `None` and which always arrives first."""
    if event.get("type") != "stream_event":
        return ""
    inner: dict[str, Any] = event.get("event") or {}
    delta: dict[str, Any] = inner.get("delta") or {}
    return str(delta.get("text") or "") if delta.get("type") == "text_delta" else ""


def check_result(event: dict[str, Any]) -> None:
    """The `result` event ends the answer, and may end it because it failed.

    A usage limit, a refused flag and a model that does not exist all arrive here with a zero
    exit code, so a caller that only looked at the exit status would write an empty narration
    into the report and call it done.
    """
    if event.get("is_error"):
        detail = str(event.get("result") or event.get("subtype") or "no reason given")
        raise NarrationFailed(f"claude ended the narration: {detail}")
