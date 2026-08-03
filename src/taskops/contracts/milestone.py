"""A milestone — the chapter a board is in, and the only thing that ends.

An objective used to be a fact like any other, and it went out of force by being SUPERSEDED: you
stated a newer one and the latest by `(ts, id)` won. Two things followed and both were wrong.
Nothing recorded whether it was reached, so a board with eight superseded objectives could not
answer "what have we shipped" — the one question a record exists for. And the decisions taken
under it floated free, attached to nothing that ends, which is how a slice grows forever.

A milestone fixes both by CLOSING, and by only closing when a person says so. It does NOT fix
them by being unique: several are active at once on any real board, and pretending otherwise
would only move the lie somewhere else. See `OPEN_MILESTONE`.

**It moves exactly like a card, and that is the same argument.** An agent creates it, works
under it, and reports it finished; a person verifies. `done` on a card already requires somebody
who is not its author, and this is that rule one level up: no count of closed cards can mean "we
shipped it". So the verbs are the card's verbs — `review`, `done`, `reject`, `cancel` — because
one state vocabulary for the whole product is learned once.

Not a table. A milestone is a fold over `milestone` events in the log that already exists, so it
replicates through `git pull`, is content-hashed against duplicate import, and keeps its own
history. `storage.milestone` is the projection.
"""

from __future__ import annotations

from typing import Literal, TypedDict, get_args

__all__ = ["MilestoneState", "STATES", "OPEN_MILESTONE", "Milestone", "MILESTONE_KIND"]

MilestoneState = Literal["planned", "in_force", "review", "reached", "abandoned"]
"""planned — written down, nobody on it yet. The todo-list: visible without being worked.
in_force — active. Cards attach to it, and its facts reach the workers holding those cards.
review — an agent reported it finished. STILL active: nothing archives on an agent's word.
reached — a person verified it. It closes, and its facts leave every slice.
abandoned — a person stopped it. Kept because "we stopped" is not "we shipped", and superseding
could not tell them apart."""

STATES: tuple[MilestoneState, ...] = get_args(MilestoneState)

OPEN_MILESTONE: tuple[MilestoneState, ...] = ("in_force", "review")
"""The two states that mean ACTIVE — being worked on right now.

**Several may be active at once**, deliberately. A team ships the importer and the invoices in
the same fortnight, and a model that allowed one chapter would have forced one of them to be
`planned` while somebody was demonstrably working on it — a board lying about what is happening,
which is the one thing a board exists not to do.

That costs the invariant a single chapter bought, and something else has to bound a worker's
slice. It does, and better: **a card belongs to exactly one milestone**, so the facts a worker is
handed are its OWN chapter's — one, whatever number are active. The bound moved from "there is
only one" to "you are only in one", which is true of the reader rather than of the board.

`review` is in here and that is load-bearing: a milestone an agent called finished is still
governing its cards, so they keep their home and its rules keep applying until a person closes
it. Nothing archives on an agent's word.
"""

MILESTONE_KIND = "milestone"
"""The event kind. Filed under `CONTEXT_TASK` like a fact — an `Event` must name a task, and a
milestone is about the project rather than about one card.

It REPLICATES: it is not in `LOCAL_ONLY_KINDS`, because which chapter a board is in is the most
shared fact there is. The channel does not forward it, which is correct rather than an omission —
a milestone move is derivable state, and `attention` is where a session reads it.
"""


class Milestone(TypedDict):
    """One chapter, as the projection reconstructs it from its events."""

    id: str
    """The CREATE event's id — a content hash, so the same id on every machine. That is what
    lets a fact created on one clone attach to a milestone created on another."""

    title: str
    """Three or five words — what somebody calls this chapter out loud. It is what the board's
    selector, a card's badge and every log line print, and it is short BECAUSE of that: the first
    version had one text field carrying a whole sentence, and every surface that had to fit it in a
    row cut it mid-word.

    A pre-0.5.0 chapter has no title — `storage.milestone` maps its `text` here, which is that
    sentence. Nothing rewrites the event: a truncated title is a display problem, a rewritten log
    is a different board."""

    goal: str
    """What "done" means, in as many words as it takes. The OUTCOME and its border — what is in,
    what is deliberately not, how anybody will know.

    Separate from `title` because they are read in different places and at different lengths, and
    one field could only ever be right for one of them. Separate from a `decision` because it is not
    a call somebody made under this chapter, it is the chapter: a goal written as a decision was the
    first version of this, and it sat in a list of technical rulings where nobody read it as the
    point of the work.

    Prose, and usually an agent's: `taskops_milestone create=… goal="…"` takes a paragraph."""

    horizon: str
    """When it is meant to be reached. Advisory: nothing expires on it, but a milestone whose
    horizon has passed and which nobody has closed is exactly the kind of thing `attention`
    exists to put in front of a person."""

    state: MilestoneState

    created_by: str
    created: float
    updated: float

    closed_by: str
    """Who VERIFIED it, and `""` until somebody did. Never the reporter: an agent moving it to
    `review` does not write this, which is the difference between "somebody says it is done" and
    "somebody who is not the author agrees"."""

    note: str
    """The message on the last move — the review report, the reject reason, the cancel reason.
    One field rather than three, because a reader wants the latest thing said about it and the
    log keeps every one of them."""
