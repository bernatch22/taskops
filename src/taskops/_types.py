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
    "LEASE_ENDS",
    "STATUSES",
    "EVENT_KINDS",
    "LOCAL_ONLY_KINDS",
    "EDITABLE_FIELDS",
    "HUMAN",
    "PEER",
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
is one indexed read rather than a graph walk per caller. `engine.scheduler.unblock`
is the ONE writer that moves a task between `backlog` and `ready`, which is what
keeps the stored value from drifting from the dependency graph — and it RECORDS the
move, so a past day's dossier can say which of the two a card was in. It did not for
a long time, and that silence is why every window before 0.5.17 reconstructs a card
sitting between those two states as `backlog`. See `engine._asof`.
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
    "context",  # a standing fact: a rule, a decision, a note, or a dev's own objective
    "milestone",  # a chapter opened, edited, reported finished, verified or abandoned
    "policy",  # a standing SETTING the engine reads, validated when written
    "landed",   # a done card's branch was merged into the trunk, or could not be
    "inferred",  # taskops attributed a call to the card's assignee, the caller named nobody
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

EDITABLE_FIELDS: tuple[str, ...] = ("title", "spec", "priority", "reviewer", "milestone")
"""The columns a person may rewrite after a card exists. Named here rather than in
`storage` because three layers ask the same question — the CLI validates a flag, the
use case records one event per field, and replay refuses a body naming anything else.

`milestone` is here so a card can CHANGE chapter, which it could not until a real board
migrated: the fold that carries a pre-0.5.0 board's facts forward does nothing for its cards, so
every one of them was `""` for ever and the board's first chapter was born empty. It rides the
same path as the other four deliberately — one event kind, one newer-wins arbitration, one
whitelisted UPDATE — rather than a second write path for one column. What it does NOT share is
validation: the others are free text, and a chapter has to exist and be active, which is
`_planinto.chapter_to_move_into`'s job and stays in the use case. Replay accepts whatever
arrives, for the same reason it accepts an unknown `reviewer` — a teammate's log is not ours to
second-guess."""

PEER = "peer"
"""A reviewer that means "anybody but this card's own developer".

Written on the card like every other reviewer, and normally not by hand: a team states it once
with `taskops policy reviewer peer` and every card created after that carries it. The policy is
where the intent lives, the field is where the engine reads it — stamping it at creation is what
keeps a policy changed today from rewriting who was allowed to close work planned last week."""

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

LEASE_ENDS: frozenset[str] = frozenset({"ready", "done", "cancelled", "review"})
"""Arriving at one of these RELEASES the lease. Stated once because it was stated twice and the
two copies drifted: `review` was added to the transition and not to the mirror that a remote
write updates, so a developer who handed a card over kept a live lease on it forever. Its own
board then read that lease as "somebody is working on this" and went silent about a card that
was waiting for a reviewer — and about the same card when it came back rejected."""

LOCAL_ONLY_KINDS: frozenset[str] = frozenset({"activity"})
"""Kinds that never reach the git-committed log. `activity` is a per-keystroke
heartbeat: replicating it through git would add thousands of lines a day to a
file whose whole value is that a human can read its diff.
"""
