"""An agent's conversation, as the card shows it.

Claude Code writes every session to a JSONL transcript. taskops does NOT copy those into its own event
log, and that is deliberate: one session here was 198 KB for 39 entries, `events.jsonl` is committed to
git, and the whole value of that file is that a human can read its diff. So the card stores a POINTER
and the transcript is read on demand.

The honest consequence, worth stating where the type is defined: a transcript is LOCAL. A teammate who
pulls the log gets the card, the commits and the conversation summary, but not the transcript — that
file only exists on the machine the agent ran on.
"""

from __future__ import annotations

from typing import Literal, TypedDict

__all__ = ["LogEntry", "SessionLog", "EntryKind"]

EntryKind = Literal["prompt", "thinking", "text", "tool", "result", "other"]
"""What one entry IS, flattened from the transcript's shape.

The raw format nests differently per role — an assistant message holds a list of content blocks, each
with its own type — and a reader wants one flat stream. `other` is the escape hatch: the format is not
documented as stable, so an entry this version does not recognise is shown rather than dropped.
"""


class LogEntry(TypedDict):
    """One turn, one thought, or one tool call."""

    kind: EntryKind
    text: str
    """The readable content. For a tool call, a one-line summary rather than the arguments — a
    dashboard showing forty lines of JSON per Edit is a dashboard nobody scrolls."""

    tool: str
    """The tool name for `kind == "tool"`, else "". Kept separate from `text` so a viewer can badge
    it without parsing prose back apart."""

    ts: float
    session: str


class SessionLog(TypedDict):
    """Everything one card's agents said, in order."""

    task: str
    sessions: list[str]
    """The session ids found for this card. More than one is normal: a card can be released and
    picked up again, and each attempt is its own session."""

    entries: list[LogEntry]
    source: str
    """Where the transcripts were read from, so a viewer showing nothing can say WHY — a missing
    directory and an empty conversation look identical otherwise."""

    truncated: bool
    """True when entries were dropped to stay under a limit. Reported rather than silent: a viewer
    that quietly showed the first hundred turns of a long session would be lying about the ending."""
