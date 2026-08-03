"""The context layer — what a worker must know that is not on its card.

The 2026 literature on agent systems is blunt about two things: a frontier model follows
roughly 150-200 standing instructions before compliance decays, and two agents working from
DIFFERENT definitions of the same rule cannot be reconciled by any supervisor. A CLAUDE.md
that grows is therefore not a direction, it is a decay curve. The answer is to treat context
as infrastructure — versioned, owned, and handed out in SLICES.

Four kinds of fact, one shape. They differ in lifetime, not in structure, so a single TypedDict
keeps the projection, the wire and the renderer from growing four near-copies.

**A fact's lifetime is declared where it is written, by `level`.** `level="project"` outlives
every milestone; `level="milestone"` dies when its chapter closes. That is the whole answer to
"does a rule survive?", and it is answered by the person writing it — who knows which it is —
rather than by a default nobody chose or a triage nobody performs.

None of this is a table. Every fact is an EVENT in the log that already exists, which is why
it replicates through `git pull` for free, is content-hashed against duplicate import, and
keeps its own history. `storage.context` is the projection that reads it back.
"""

from __future__ import annotations

from typing import Literal, TypedDict, get_args

__all__ = ["Sort", "SORTS", "Level", "LEVELS", "Fact", "CONTEXT_TASK", "CONTEXT_KIND"]

Sort = Literal["objective", "rule", "decision", "note"]
"""objective — what ONE DEV is chasing inside the open chapter. The project's north is not here:
it is a `Milestone`, because a thing you reach and a thing you cannot finish are different nouns
and calling both "objective" is what let one silently replace the other.
rule — never broken. Unscoped by nature; scoping one narrows what it governs.
decision — what was decided and why (ADR-lite), so a settled question is not re-litigated.
note — standing, and neither a goal nor a rule. Always `level="milestone"`: if it is permanent it
is a rule or a decision, and a note that outlived its chapter is the scratchpad that made a
slice grow forever.

`rule` came back, and it is not the `invariant` that was removed in 0.4.0. That one was a
LIFETIME masquerading as a category — it skipped the subject filter, and nothing else — so it
collapsed into "a decision with no scope". This one is a NAME for the thing at either level:
`level="project"` for what is true in 2027, `level="milestone"` for what is true until this ships.
The word is worth having now because the two lifetimes are real; it was not worth having when the
only difference was a filter.
"""

Level = Literal["project", "milestone"]
"""Where a fact lives, and therefore how long. `project` outlives every chapter; `milestone`
belongs to the one open when it was written and leaves every slice when that chapter closes.

The default is `milestone`, deliberately, and the direction matters: a fact that dies with its
chapter is recovered by restating it, and one that lives forever accumulates silently — which is
the failure this whole model exists to end. The default falls on the recoverable side.
"""

LEVELS: tuple[Level, ...] = get_args(Level)

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
"""One event kind for all four sorts, with the sort in the body.

Four kinds would be four entries in `EventKind`, four cases in every renderer, and no gain: a
reader that cares about the difference is already reading the body for the text.
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

    milestone: str
    """The chapter this fact belongs to, or `""` for a `level="project"` fact and for anything
    written before milestones existed.

    Resolved AT WRITE TIME from the chapter in force, never chosen: there is only one open, so
    nobody can attach a fact to the wrong chapter and no caller needs an argument for it.
    """

    level: Level

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
