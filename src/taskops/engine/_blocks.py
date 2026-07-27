"""Reading the CONTENT of a transcript entry: a tool call's arguments, a tool result's payload.

Split from `_entries` by depth rather than by topic. That module walks the entry's shape and decides
what each line IS; this one reaches inside a block and decides what to SHOW of it — which is where the
judgement about brevity lives, and the part that gets tuned after looking at a real dashboard.
"""

from __future__ import annotations

from typing import Any, cast

__all__ = ["summarise", "result_text"]

_IDENTIFYING = ("file_path", "command", "path", "pattern", "query", "task", "prompt")
"""Argument names that say WHICH thing a tool acted on, in the order they are worth showing.

`file_path` first because Read/Write/Edit are most of any transcript, then `command` for Bash. A call
whose arguments contain none of these falls back to naming its keys, which at least says what shape it
had.
"""


def summarise(tool: str, arguments: object) -> str:
    """A tool call in ONE line: the argument that identifies it, never the whole payload.

    A dashboard showing the full `input` of every Edit is a dashboard nobody scrolls — the diff is
    already in git, and what a reader wants here is which file was touched.
    """
    if not isinstance(arguments, dict):
        return tool
    args = cast("dict[str, Any]", arguments)
    for key in ("file_path", "command", "path", "pattern", "query", "task", "prompt"):
        found = args.get(key)
        if isinstance(found, str) and found.strip():
            return f"{found.strip()[:200]}"
    return ", ".join(sorted(args)[:4])


def result_text(content: object) -> str:
    """A tool result, which arrives as a string or as a list of blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        blocks = cast("list[object]", content)
        parts = [str(cast("dict[str, Any]", block).get("text", ""))
                 for block in blocks if isinstance(block, dict)]
        return "\n".join(part for part in parts if part)
    return ""
