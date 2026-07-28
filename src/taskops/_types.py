"""Layer 0 — the vocabulary. Every state and every event kind, named once.

These are `Literal`s rather than enums on purpose: the values cross a JSON
boundary in both directions (the MCP wire, the event log in git, the studio's
fetch), and a Literal IS the wire value, so there is no encode/decode step where
a rename can half-land. The MCP `inputSchema` generator turns them into an
`enum`, which is how an agent learns the allowed values before it guesses one.

Imports nothing from the package, so any layer may import it without thinking
about cycles. `tests/architecture` enforces that.
"""

from __future__ import annotations

from typing import Literal, get_args

__all__ = [
    "Status",
    "ActorKind",
    "EventKind",
    "OPEN_STATUSES",
    "CLOSED_STATUSES",
    "WORKING_STATUSES",
    "STATUSES",
    "EVENT_KINDS",
    "LOCAL_ONLY_KINDS",
    "EDITABLE_FIELDS",
]

Status = Literal[
    "backlog", "ready", "claimed", "in_progress", "blocked", "review", "done", "cancelled"
]
"""Where a task is. See `engine.machine` for which moves between these are legal.

`ready` is a stored status and not a derived view, so that "what can I pick up"
is one indexed read rather than a graph walk per caller. `engine.machine.unblock`
is the ONE writer that moves a task between `backlog` and `ready`, which is what
keeps the stored value from drifting from the dependency graph.
"""

ActorKind = Literal["dev", "agent"]
"""A human or one of their agents. The distinction is not cosmetic: guards that
demand a justification accept one from a dev and reject it from an agent."""

EventKind = Literal[
    "created",
    "claimed",
    "released",
    "status",
    "comment",
    "commit",
    "branch",
    "blocked",
    "unblocked",
    "handoff",
    "review",
    "eval",
    "done",
    "message",  # directed chat: agent↔agent, dev↔agent
    "activity",  # a session's heartbeat: a tool ran, a file was touched
    "edited",  # a field of the card itself changed: title, spec or priority
]
"""What happened. The event log is append-only and every projection — the board,
a standup, an inbox — is derived from it, so a new fact about a task is a new
kind here rather than a column somewhere."""

STATUSES: tuple[Status, ...] = (
    "backlog",
    "ready",
    "claimed",
    "in_progress",
    "blocked",
    "review",
    "done",
    "cancelled",
)

EVENT_KINDS: tuple[EventKind, ...] = get_args(EventKind)
"""The same values as the `Literal`, DERIVED rather than retyped.

Two hand-written lists is how a kind ends up legal at the type level and unknown to the
MCP schema that iterates the tuple — a mismatch nothing catches, because the type check
passes and the runtime list is merely short. `STATUSES` keeps its literal spelling: it is
also the display order, which is a separate decision that happens to agree today."""

EDITABLE_FIELDS: tuple[str, ...] = ("title", "spec", "priority")
"""The columns a person may rewrite after a card exists. Named here rather than in
`storage` because three layers ask the same question — the CLI validates a flag, the
use case records one event per field, and replay refuses a body naming anything else."""

OPEN_STATUSES: frozenset[str] = frozenset(
    {"backlog", "ready", "claimed", "in_progress", "blocked", "review"}
)
"""A dependency in one of these still blocks whatever waits on it."""

CLOSED_STATUSES: frozenset[str] = frozenset({"done", "cancelled"})
"""`cancelled` closes a dependency as surely as `done` does: a task nobody will
ever do must not hold its dependents hostage forever."""

WORKING_STATUSES: frozenset[str] = frozenset({"claimed", "in_progress", "review"})
"""Statuses that require a live lease. Losing the lease drops the task out."""

LOCAL_ONLY_KINDS: frozenset[str] = frozenset({"activity"})
"""Kinds that never reach the git-committed log. `activity` is a per-keystroke
heartbeat: replicating it through git would add thousands of lines a day to a
file whose whole value is that a human can read its diff."""
