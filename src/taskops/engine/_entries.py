"""One raw transcript entry -> one flat `LogEntry`. The shape-flattening, on its own.

The raw format nests differently per role: an assistant entry holds `message.content`, a LIST of blocks
each with its own type (`thinking`, `text`, `tool_use`), while a user entry's content may be a plain
string or a list containing `tool_result`. A reader wants one flat stream in time order, so one raw
entry can produce several `LogEntry`s.

Split from `transcript` because that module answers "where is the file" and this one answers "what does
a line mean" — and the second is the half that will need editing when the format moves.

Nothing is dropped. An entry this version does not recognise becomes `other` with whatever text can be
salvaged, because the format is not documented as stable and a silently shorter conversation is worse
than an odd-looking line.
"""

from __future__ import annotations

from typing import Any, cast

from ..contracts import LogEntry
from ._blocks import result_text, summarise
from .transcript import clip

__all__ = ["flatten"]

_SKIP = frozenset({"mode", "permission-mode", "ai-title", "last-prompt", "queue-operation",
                   "file-history-snapshot", "file-history-delta", "attachment"})
"""Entry types that are Claude Code's own bookkeeping, not conversation.

Verified against a real 1018-line transcript, where these were a third of it: mode switches, the
generated title, snapshots of files for undo. Keeping them would bury the twenty entries a person
actually wants to read.
"""


def flatten(entry: dict[str, Any]) -> list[LogEntry]:
    """Zero, one, or several readable entries from one raw line."""
    kind = str(entry.get("type", ""))
    if kind in _SKIP:
        return []
    session = str(entry.get("sessionId") or entry.get("session_id") or "")
    ts = _time(entry)
    message = entry.get("message")
    if not isinstance(message, dict):
        return _fallback(entry, session, ts)
    return _from_message(cast("dict[str, Any]", message), kind, session, ts)


def _from_message(message: dict[str, Any], kind: str, session: str,
                  ts: float) -> list[LogEntry]:
    content = message.get("content")
    if isinstance(content, str):
        return _entry("prompt" if kind == "user" else "text", content, "", ts, session)
    if not isinstance(content, list):
        return []
    out: list[LogEntry] = []
    for block in cast("list[object]", content):
        if isinstance(block, dict):
            out += _from_block(cast("dict[str, Any]", block), kind, session, ts)
    return out


def _from_block(block: dict[str, Any], kind: str, session: str,
                ts: float) -> list[LogEntry]:
    """One content block. The four shapes that actually occur, plus a catch-all."""
    shape = str(block.get("type", ""))
    if shape == "thinking":
        return _entry("thinking", str(block.get("thinking", "")), "", ts, session)
    if shape == "text":
        return _entry("prompt" if kind == "user" else "text",
                      str(block.get("text", "")), "", ts, session)
    if shape == "tool_use":
        name = str(block.get("name", "?"))
        return _entry("tool", summarise(name, block.get("input")), name, ts, session)
    if shape == "tool_result":
        return _entry("result", result_text(block.get("content")), "", ts, session)
    return _entry("other", shape, "", ts, session) if shape else []


def _fallback(entry: dict[str, Any], session: str, ts: float) -> list[LogEntry]:
    """An entry with no `message`: system notices and anything new.

    Kept rather than dropped, because the alternative is a conversation that is quietly missing the
    line that explained why it stopped.
    """
    for key in ("content", "text", "summary"):
        found = entry.get(key)
        if isinstance(found, str) and found.strip():
            return _entry("other", found, "", ts, session)
    return []


def _entry(kind: str, text: str, tool: str, ts: float,
           session: str) -> list[LogEntry]:
    """One entry, or NONE when there is nothing to show.

    Empty content is dropped, and `thinking` is why. Extended thinking is REDACTED in the transcript —
    the block keeps its `signature` and its `thinking` field is the empty string — so rendering it
    produced a blank `· thinking` line before every single assistant turn. That is not a formatting
    nit: it doubled the length of the log with rows that say nothing, and it looked like taskops had
    failed to read something rather than like there being nothing to read.

    A `tool` entry survives an empty text, because the tool NAME is the content there.
    """
    body = clip(text)
    if not body and kind != "tool":
        return []
    return [LogEntry(kind=kind,               # type: ignore[typeddict-item]
                     text=body, tool=tool, ts=ts, session=session)]


def _time(entry: dict[str, Any]) -> float:
    """The entry's timestamp as epoch seconds, or 0.

    The transcript writes ISO 8601; the rest of taskops uses epoch floats, so converting here keeps
    every consumer on one clock.
    """
    from datetime import datetime

    raw = entry.get("timestamp")
    if not isinstance(raw, str):
        return 0.0
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0
