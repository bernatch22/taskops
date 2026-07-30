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
    "HUMAN",
]

Status = Literal[
    "backlog", "ready", "claimed", "blocked", "review", "done", "cancelled"
]
"""Where a task is. See `engine.machine` for which moves between these are legal.

`in_progress` was here and is gone. It meant "claimed and actually working", which is what
`claimed` already meant to everyone who used the board: ONE transition to it in the whole
history of this project, written by hand in a test. A state nobody enters is a column that
splits attention and answers nothing. A log that still carries it replays as `claimed` — see
`engine.replay` — because that is what it always was.

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
    "acceptance",  # what a card promises: its EARS criteria, restated whole
    "context",  # a standing fact about the PROJECT: an objective, invariant or decision
    "inferred",  # taskops attributed a call to the card's assignee, the caller named nobody
    "chat",  # a line said to the open session from the board's sidebar, about no card
]
"""What happened. The event log is append-only and every projection — the board,
a standup, an inbox — is derived from it, so a new fact about a task is a new
kind here rather than a column somewhere."""

STATUSES: tuple[Status, ...] = (
    "backlog",
    "ready",
    "claimed",
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

EDITABLE_FIELDS: tuple[str, ...] = ("title", "spec", "priority", "reviewer")
"""The columns a person may rewrite after a card exists. Named here rather than in
`storage` because three layers ask the same question — the CLI validates a flag, the
use case records one event per field, and replay refuses a body naming anything else."""

HUMAN = "human"
"""What a card's `reviewer` says when a PERSON closes it — "whoever is reading the board".

Layer 0 because two layers spell it: the use case that validates a reviewer as it is written,
and the closing guard that refuses an agent when it reads one. A second literal in the engine
would be a rule that agrees with the writer only until somebody edits one of them.

Not normalised into a `dev:` id: the session naming it does not know who will pick the card
up, and it is what a person actually types."""

OPEN_STATUSES: frozenset[str] = frozenset(
    {"backlog", "ready", "claimed", "blocked", "review"}
)
"""A dependency in one of these still blocks whatever waits on it."""

CLOSED_STATUSES: frozenset[str] = frozenset({"done", "cancelled"})
"""`cancelled` closes a dependency as surely as `done` does: a task nobody will
ever do must not hold its dependents hostage forever."""

WORKING_STATUSES: frozenset[str] = frozenset({"claimed", "review"})
"""Statuses that require a live lease. Losing the lease drops the task out."""

LOCAL_ONLY_KINDS: frozenset[str] = frozenset({"activity", "chat"})
"""Kinds that never reach the git-committed log. `activity` is a per-keystroke
heartbeat: replicating it through git would add thousands of lines a day to a
file whose whole value is that a human can read its diff.

`chat` is here for the opposite reason — not volume, CONTENT. It is a box where a
person types half-formed thinking at the speed of a terminal prompt, and an
append-only replicated log has no eraser. What deserves to be read by the team goes
in a comment or a context fact, deliberately. See `usecases.chat` for the full
argument, including the one it was weighed against."""
