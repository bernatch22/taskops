"""An agent's conversation, rendered for a person catching up on a card.

Shaped by what a reader is actually asking: not "replay everything", but "what did it decide, what did
it touch, and how did it end". So thinking is marked as thinking, a tool call is one line naming the
file, and the whole thing reads top-down like a transcript rather than like a data dump.
"""

from __future__ import annotations

from ..contracts import LogEntry, SessionLog
from ._text import ago

__all__ = ["render_log"]

_MARK = {"prompt": "▸ you", "thinking": "· thinking", "text": "◆ agent",
         "tool": "→", "result": "  ←", "other": "·"}
"""One marker per kind. `result` is indented because it belongs to the call above it, which is the
only structure in the stream a reader needs to see."""

_RESULT_LINES = 3
"""Lines kept from a tool result. They are the longest entries by far and the least read — a file's
contents came back from a Read, and the reader is looking for what the agent DID with it."""


def render_log(log: SessionLog) -> str:
    if not log["entries"]:
        return f"# {log['task']} — no conversation found\n\n{log['source']}"
    head = [f"# {log['task']} — conversation", "",
            f"_{len(log['entries'])} entries · {len(log['sessions'])} session(s)"
            + (" · TRUNCATED to the most recent" if log["truncated"] else "") + "_", ""]
    return "\n".join(head + [_entry(e) for e in log["entries"]])


def _entry(entry: LogEntry) -> str:
    mark = _MARK.get(entry["kind"], "·")
    when = ago(entry["ts"]) if entry["ts"] else ""
    if entry["kind"] == "tool":
        return f"{mark} **{entry['tool']}** `{entry['text']}`"
    if entry["kind"] == "result":
        return f"{mark} {_short(entry['text'])}"
    return f"\n{mark} _{when}_\n{entry['text']}\n"


def _short(text: str) -> str:
    lines = [line for line in text.splitlines() if line.strip()][:_RESULT_LINES]
    joined = " / ".join(line.strip()[:120] for line in lines)
    return joined or "(empty)"
