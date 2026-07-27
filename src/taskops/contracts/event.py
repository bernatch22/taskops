"""The event — the only thing taskops actually stores.

The board, a standup, an inbox and a burndown are all PROJECTIONS of this table.
That is what makes "who decided this and when" answerable months later, and it is
why adding a fact about a task is a new `kind` rather than a column somewhere.

The id is the content, hashed (`_ids.event_id`), so the same event arriving twice
— once through `git pull`, once through the relay — is a primary-key no-op rather
than a duplicate comment in somebody's inbox.
"""

from __future__ import annotations

from typing import Any, TypedDict

from .._types import EventKind

__all__ = ["Event", "Inbox"]


class Event(TypedDict):
    """One thing that happened, attributed and timestamped."""

    id: str
    task: str
    """The task it is about. Never empty: an event with no task cannot be found
    again by anyone looking at the work, and project-wide facts belong in `meta`."""

    actor: str
    kind: EventKind

    body: dict[str, Any]
    """The payload, shaped by `kind` — `{sha, message, files}` for a commit,
    `{text, mentions}` for a comment, `{from, to}` for a status change.

    Deliberately open rather than a tagged union of thirteen TypedDicts: a reader
    that does not know a kind must be able to store and forward it untouched,
    because a newer taskops on a teammate's machine WILL write kinds this one has
    never heard of into the shared log. Renderers read the keys they know.
    """

    ts: float


class Inbox(TypedDict):
    """What an actor has not been shown yet.

    Delivery is tracked per (actor, event) rather than by a timestamp cursor: an
    agent's hooks fire in an order nobody controls, and a cursor would silently
    skip anything that arrived out of order.
    """

    actor: str
    messages: list[Event]
    """Directed at this actor — mentions and handoffs, oldest first."""

    tasks: list[str]
    """The tasks those messages are about, deduplicated, for the render's header."""
