"""The context layer — what a worker must know that is not on its card.

The 2026 literature on agent systems is blunt about two things: a frontier model follows
roughly 150-200 standing instructions before compliance decays, and two agents working from
DIFFERENT definitions of the same rule cannot be reconciled by any supervisor. A CLAUDE.md
that grows is therefore not a direction, it is a decay curve. The answer is to treat context
as infrastructure — versioned, owned, and handed out in SLICES.

Three kinds of fact, one shape. They differ in lifetime, not in structure, so a single
TypedDict keeps the projection, the wire and the renderer from growing three near-copies.

None of this is a table. Every fact is an EVENT in the log that already exists, which is why
it replicates through `git pull` for free, is content-hashed against duplicate import, and
keeps its own history. `storage.context` is the projection that reads it back.
"""

from __future__ import annotations

from typing import Literal, TypedDict, get_args

__all__ = ["Sort", "SORTS", "Fact", "ContextSlice", "CONTEXT_TASK", "CONTEXT_KIND"]

Sort = Literal["objective", "invariant", "decision"]
"""objective — what we are chasing now; superseded, never deleted.
invariant — what must never break; long-lived, and what EVERY worker gets.
decision — what was decided and why (ADR-lite), so a settled question is not re-litigated."""

SORTS: tuple[Sort, ...] = get_args(Sort)
"""Derived, not retyped: a second hand-written list is how a sort becomes legal to the type
checker and unknown to the validator that iterates the tuple."""

CONTEXT_TASK = "project"
"""The `task` every context event is filed under.

An `Event` must name a task — an event with no task cannot be found again by anyone looking
at the work. Context facts are about the PROJECT, so they share one sentinel id rather than
an empty string: `events.of_task("project")` is then the whole context history, one indexed
read, and nothing has to special-case a blank column.
"""

CONTEXT_KIND = "context"
"""One event kind for all three sorts, with the sort in the body.

Three kinds would be three entries in `EventKind`, three cases in every renderer, and no
gain: a reader that cares about the difference is already reading the body for the text.
"""


class Fact(TypedDict):
    """One standing statement, as the projection reconstructs it from its event."""

    id: str
    """The EVENT id — the content hash. So it is the same id on every machine, which is what
    lets `retire` on one clone refer to a fact created on another."""

    sort: Sort
    text: str

    labels: list[str]
    files: list[str]
    """The scope. Empty means project-wide, which is why an invariant normally carries
    neither: `context_for` must never drop one. A decision scoped to labels or to an edit
    surface reaches only the cards that share them."""

    horizon: str
    owner: str
    """Only an objective usually fills these — when it expires and whose call it is."""

    actor: str
    ts: float

    retired: bool
    """Withdrawn by a later event. An event log has no eraser: the fact keeps existing, it
    just stops being in force, and `context log` still shows it."""


class ContextSlice(TypedDict):
    """What one worker is handed: not the book, the page that applies to its card."""

    objective: Fact | None
    invariants: list[Fact]
    decisions: list[Fact]
