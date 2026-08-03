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

Sort = Literal["objective", "decision", "note"]
"""objective — what we are chasing now; superseded, never deleted.
decision — what was decided and why (ADR-lite), so a settled question is not re-litigated.
note — anything standing that is none of those: a habit, a warning, a thing worth remembering.
Usually somebody's OWN, which is what it is for — the other two are statements about the
project and this is the one that does not have to be.

`invariant` was a fourth and is gone. It meant "never break this, and it reaches EVERY card" —
and the second half was the only mechanical difference: an invariant skipped the subject filter
that narrows a decision. But a decision with no `labels` and no `files` already reaches every
card (`_contextslice._applies` returns True for an unscoped fact), so an invariant was a
scopeless decision plus a word saying "this one is not up for debate". Four categories to
choose between is a choice somebody makes wrong, and the tie-break they need is not there:
what actually REFUSES is a policy, which the engine validates and obeys. Prose does not refuse.

Facts already written as invariants are read as decisions — see `storage.context` — and their
scope is dropped on the way, because "reaches everything" was their meaning and a remapped
fact that suddenly stopped reaching everything would be a silent behaviour change on a live
board. The cost of the whole removal is one lost guarantee: a rule that must reach every card is
now an UNSCOPED decision, and scoping it silently narrows it. That was impossible before."""

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
    """The scope. Empty means project-wide, which is why a standing rule carries
    neither: `context_for` must never drop one. A decision scoped to labels or to an edit
    surface reaches only the cards that share them."""

    horizon: str
    """When an objective expires. Only an objective usually fills it."""

    owner: str
    """Whose fact this is — `dev:ana` — or "" for the project's.

    The SECOND dimension of scope, and it works the same for all four sorts: a fact with an
    owner reaches that dev and nobody else, one without reaches everybody. `labels`/`files`
    narrow by SUBJECT, this narrows by PERSON, and a fact can carry both.

    What it protects is the size of a slice. Three developers each stating their own objective
    must not make every worker read four: everybody reads the project's and their own, so the
    page grows by one no matter how many people are on the board.
    """

    actor: str
    ts: float

    retired: bool
    """Withdrawn by a later event. An event log has no eraser: the fact keeps existing, it
    just stops being in force, and `context log` still shows it."""


class ContextSlice(TypedDict):
    """What one worker is handed: not the book, the page that applies to its card."""

    objective: Fact | None
    """The PROJECT's — the north, which everybody reads whatever they are holding."""

    yours: Fact | None
    """The objective of whoever holds this card, when they have set one. Beside the project's
    and not instead of it: "the team is shipping the importer" and "I am on the parser this
    week" are both true, and a worker that only read the second lost the first."""

    objectives: list[Fact]
    """Every objective in force, the project's and one per dev. For the OVERVIEW — `context
    show`, the board — never for a worker's slice: it is what answers "who is on what" when you
    are deciding who to hand a card to."""
    decisions: list[Fact]
    notes: list[Fact]
