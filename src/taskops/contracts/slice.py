"""What ONE reader is handed — the page, not the book.

Split from `context` when the two together stopped fitting one screen, and the split names two
different things: that module is what a FACT is, this is what a READER gets. They change for
different reasons — a new sort touches one, a new bound touches the other.

Re-exported from `contracts.context` so no caller had to move.
"""

from __future__ import annotations

from typing import NamedTuple, TypedDict

from .context import Fact
from .milestone import Milestone

__all__ = ["ContextSlice", "Chapters"]


class ContextSlice(TypedDict):
    """What one worker is handed: not the book, the page that applies to its card.

    Two bounds, and both are now structural rather than advisory. The OWNER filter keeps a slice
    growing by one whatever the size of the team — everybody reads the project's facts and their
    own. The CHAPTER keeps it from growing with the year: a decision taken in March stops being
    injected when the milestone it belonged to is reached, and nobody has to retire it by hand.

    The project block is separate from the chapter block on purpose. Those facts are true
    whatever anybody is working on, so a reader must not have to infer that they outlive the
    thing they are printed next to.
    """

    milestone: Milestone | None
    """The chapter THIS slice is for: a card's own, or None for an overview and for a board that
    has no milestone yet — a state the renderers name rather than hide, because `plan` refuses
    without one.

    Singular even though several may be active, and that is the bound. A card belongs to exactly
    one milestone, so a worker is handed one chapter's facts however many the board is running.
    """

    active: list[Milestone]
    """Every chapter being worked on — `in_force` or `review`. Several is normal.

    Read by the ORCHESTRATOR, which is the one reader that has to choose between them: it plans
    into one, dispatches from one, and needs to see all of them to do either. A worker never
    reads this list; it reads `milestone`, which is its card's.
    """

    counts: dict[str, dict[str, int]]
    """Cards by status, keyed by milestone id. What makes a milestone a todo-list to a reader who
    cannot see the board: `7 cards · 3 done` is a count, not an opinion. Keyed rather than flat
    because with several active, "how far along" is a question per chapter."""

    planned: list[Milestone]
    """Written down and not started. Titles only in every renderer — a planned chapter carries no
    facts and no cards, and printing more of it would let it read as something to work on."""

    project_rules: list[Fact]
    project_decisions: list[Fact]
    """`level="project"`. Permanent, never narrowed by chapter. Rules are never narrowed by
    subject either — a decision that misses a card costs a re-litigation, a rule that misses one
    costs the breakage it existed to prevent."""

    rules: list[Fact]
    decisions: list[Fact]
    notes: list[Fact]
    """The chapter's own. In a CARD slice, `decisions` and `notes` are narrowed by subject and
    `rules` are not. Notes are narrowed too, which they were not before 0.5.0: a note scoped to
    `[importador]` was reaching cards about the parser, so the scope somebody bothered to write
    meant nothing."""

    yours: Fact | None
    """The reader's own objective, when they have set one. Beside the milestone and not instead
    of it: "the team is shipping the importer" and "I am on the parser this week" are both true,
    and a worker that only read the second lost the first."""

    objectives: list[Fact]
    """Every dev's objective in the open chapter. For the OVERVIEW — `context show`, the board —
    and NEVER for a worker's slice: handing one worker four people's objectives is exactly what
    the owner filter exists to prevent."""


class Chapters(NamedTuple):
    """The milestone side of a slice, resolved by the caller.

    A NamedTuple and not three parameters because they always travel together and always come
    from the same fold — and because this module stays PURE: it may not open a store to ask which
    chapters are active, so what it cannot look up it is handed.
    """

    active: list[Milestone]
    planned: list[Milestone]
    counts: dict[str, dict[str, int]]


def chapters_of(active: list[Milestone], planned: list[Milestone],
                counts: dict[str, dict[str, int]]) -> Chapters:
    return Chapters(active=active, planned=planned, counts=counts)
