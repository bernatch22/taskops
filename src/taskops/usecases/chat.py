"""Talking to the session that is open — a conversation with no card under it.

**Where it lives.** In the event log, like everything else, filed under the SAME sentinel task
`context` uses (`CONTEXT_TASK == "project"`). An `Event` must name a task, and a chat line is
about the project rather than about one card, so the sentinel is exactly the case it was
introduced for: `events.of_task("project", kinds=("chat",))` is one indexed read, no column is
special-cased, and nothing new had to be stored. Sharing the sentinel with context costs
nothing — that projection filters by `kind`, so the two never see each other's rows.

**And why it does NOT replicate.** `chat` is in `LOCAL_ONLY_KINDS`, so it never reaches the
git-committed log, and that is a deliberate trade against the obvious virtue of the alternative.
Replicating would mean a teammate reads the reasoning, which is real value — but the log's whole
worth is that a human can read its diff, and this is a box where a person types half-formed
thinking at the speed of a terminal prompt. People write things in a chat they would not commit,
and an append-only replicated log has no eraser: publishing is irreversible, keeping it local is
not. What deserves to survive already has two durable, deliberately-shared homes one click away
— a comment on the card, or a context fact — and promoting a line into one of those is a choice
somebody makes, which is the correct shape for "the whole team will read this forever".
The same line also keeps chatter out of the daily reports, which fold over the same set.

Reversing this decision is deleting `"chat"` from that frozenset. Reversing the other one is
asking a colleague to forget what they read.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from .._errors import BadRequest
from .._types import EventKind
from ..contracts import Event
from ..contracts.context import CONTEXT_TASK
from ..engine import record
from ._project import caller, heartbeat, project

__all__ = ["CHAT_TASK", "CHAT_KIND", "say", "BOARD", "SESSION", "thread", "open_conversation",
           "current_conversation"]

CHAT_TASK = CONTEXT_TASK
"""The sentinel task chat is filed under — the project itself, not any one card."""

CHAT_KIND = cast("EventKind", "chat")
"""The cast names the one place the kind enters the log, like `context` does: `EventKind` is a
Literal in layer 0 and a use case may not widen it."""

BOARD = "board"
SESSION = "session"
"""The two doors into this conversation: somebody typing in the sidebar, and the Claude Code
session answering through the channel. Named here because three layers spell them — the use
case, the HTTP route and the renderer that has to tell them apart."""

WINDOW = 200
"""How much of the conversation a newly opened sidebar is handed. A chat is read from the
bottom, and a year of it would be a megabyte to draw the last six lines."""


def say(start: Path | str, text: str, *, card: str = "", actor: str = "",
        source: str = BOARD) -> Event:
    """Post one line. `card` is what the board was showing — context, never a parent.

    The actor is RESOLVED and never taken from the request, for the reason `post_comment` gives:
    a browser that could name its own actor could speak as somebody else's agent.

    `source` is what the actor cannot say, and the reason this parameter exists. Both sides of
    this conversation come through the same door on the same machine — the person types in the
    sidebar, the session answers through the channel's `reply` — so both resolve to the SAME
    developer id, and the answer arrived looking exactly like the question. Not invisible:
    indistinguishable, which reads as nothing having happened.

    It labels a DOOR, not a person, and grants nothing: a browser could post `session` and the
    only consequence is one mislabelled line. That is why it may ride in the request while the
    actor may not.
    """
    said = text.strip()
    if not said:
        raise BadRequest("a chat message needs text")
    body: dict[str, Any] = {"text": said, "card": card.strip(),
                            "source": SESSION if source == SESSION else BOARD}
    with project(start) as store:
        who = caller(store, actor)["id"]
        heartbeat(store, who)
        return record(store, task=CHAT_TASK, actor=who, kind=CHAT_KIND, body=body)


def open_conversation(start: Path | str, *, actor: str = "") -> str:
    """Start a new conversation and return its id. The old one stays exactly where it was.

    Called by the channel when a session starts — the channel IS that session's MCP server, so
    it is born and dies with it and needs nothing else to know when a conversation begins — and
    by the sidebar's own button, which is what "clear" means in a log with no eraser. Nothing is
    deleted: yesterday's conversation is still there, still readable, and simply not what the
    sidebar is showing.
    """
    with project(start) as store:
        who = caller(store, actor)["id"]
        heartbeat(store, who)
        started = record(store, task=CHAT_TASK, actor=who, kind=CHAT_KIND,
                         body={"text": "", "card": "", "source": SESSION, "opens": True})
        return started["id"]


def current_conversation(start: Path | str) -> str:
    """The id of the conversation in force, or "" when nobody has opened one.

    Derived, not stored: the newest `opens` marker in the log IS the answer, so there is no
    second place that could disagree with it and nothing to migrate on an old project — a board
    that predates conversations has no marker and gets its whole history, which is what it had.
    """
    with project(start) as store:
        markers = [e for e in store.events.of_task(CHAT_TASK, kinds=(CHAT_KIND,))
                   if e["body"].get("opens")]
        return markers[-1]["id"] if markers else ""


def thread(start: Path | str, *, limit: int = WINDOW, everything: bool = False) -> list[Event]:
    """The conversation in force, oldest first — the tail of it, which is what a sidebar shows.

    `everything` is the escape hatch for reading back: a new session must not open onto
    yesterday's argument, and yesterday's argument must not be gone.
    """
    with project(start) as store:
        said = store.events.of_task(CHAT_TASK, kinds=(CHAT_KIND,))
    if not everything:
        opened = [i for i, e in enumerate(said) if e["body"].get("opens")]
        said = said[opened[-1] + 1:] if opened else said
    return said[-limit:]
