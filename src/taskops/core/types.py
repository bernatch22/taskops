"""The whole data model, in one file.

These TypedDicts ARE the database row and the wire format at once — there is
no ORM layer and no hand-written encoder/decoder pair. v1 used plain classes
for `recover` and needed an encoder, a decoder and a Protocol in the renderer
to carry the same three fields.

`KINDS` is the single registry of event kinds. v1 spread the same facts across
four hand-maintained tuples (`REPLAYED`, `SAYS_STATUS`, `LOCAL_ONLY_KINDS`,
`WORK`) and they drifted. There is deliberately no `LOCAL_ONLY_KINDS` here:
every event lives wherever the log lives.

The actor grammar lives in `actors.py` and is re-exported here, so `types`
stays the one name a caller has to know.
"""

from __future__ import annotations

from typing import Any, TypedDict, NamedTuple, NotRequired

from .actors import (
    ANON,
    SYSTEM,
    ROLE_DEV,
    ROLE_ANON,
    ROLE_AGENT,
    ROLE_SYSTEM,
    role_of,
    slugify,
)

__all__ = [
    "Card", "Milestone", "Event", "Lease", "Kind", "KINDS",
    "CARD_STATUSES", "DERIVED_STATES", "MILESTONE_STATUSES", "CLOSED",
    "LEASE_TTL", "PROJECT", "SYSTEM", "ANON", "EDITABLE", "LIST_FIELDS",
    "ROLE_DEV", "ROLE_AGENT", "ROLE_SYSTEM", "ROLE_ANON", "role_of", "slugify",
]


class Card(TypedDict):
    """A unit of work. Flat on purpose: this IS the row and the wire format."""

    id: str  # "tk-" + 6 hex
    title: str  # a label

    spec: str
    """The brief, complete enough that an agent reads it and needs nothing else.

    The most important field in the system and the one most often written badly.
    A title is a label; a spec says what done looks like, what must NOT change,
    and where to look — because the reader is a fresh context that was not in the
    room when the work was decided.
    """

    criteria: list[str]
    """What this card is accepted against — the other half of the spec: the spec
    says what to build, this says what will be checked. Empty for a card that
    promised nothing checkable, which is most of them.

    A checklist, NOT a gate: v1 made `done` demand evidence per criterion and
    then refused with criteria the worker had never been shown. Here they are
    shown, right under the spec, and closing is still one honest sentence.
    """

    status: str
    """open | done | dropped — and NOTHING else.

    There is no stored `doing`, on purpose. "Somebody is working on this" is a
    LIVE fact (who holds the lease), not a row: written down, it survives the
    worker that wrote it and the card sits there claiming to be worked on by a
    process that died — which is what a `recover` verb then exists to paper over.
    Derived from the lease, a dead worker's card comes back on its own.
    """

    review: NotRequired[bool]
    """This card must be REVIEWED before it can close. OFF by default, and
    optional in the row (a card written before the feature reads as False).

    A durable fact, not a state: "handed in", "being reviewed" and "changes
    requested" are all derived from the thread (`core/review.py`) and the live
    review lease — a stored `in_review` would be a stored `doing` all over
    again. Readers use `card.get("review")`, never `card["review"]`.
    """
    priority: int  # 0 urgent … 3 someday; lower sorts first
    milestone: str  # the chapter; every card belongs to one
    parent: str | None  # the epic's id. The TREE; `after` is the DAG.
    after: list[str]  # dependencies: these must close first
    files: list[str]  # the edit surface as the planner understands it — a hint, never a lock
    labels: list[str]  # routing and search; anybody may edit them
    assignee: str  # "" is the open pool; dispatch writes it. NOT a claim — the lease is.
    created_by: str
    created: float
    updated: float  # the replay arbiter (newer-wins)


class Milestone(TypedDict):
    id: str
    title: str
    goal: str  # the WHY — it travels inside every take

    rules: list[str]
    """What holds for EVERY card of this chapter — and travels into every take.

    The chapter's half of the spec: "Decimal, never float", "no migrations in
    this milestone". Deliberately a flat list of sentences, not v1's context
    layer (four sorts × two lifetimes × a `retire` event) — that layer shipped
    and was used ZERO times on the real board.
    """

    criteria: list[str]
    """What the CHAPTER is accepted against — `rules`' sibling: spec, not
    status. Cards each measured their own part and six greens summed to a
    placeholder page (docs/fan-out.md §4), so the whole gets its own checklist.

    Shown to the human at `taskops_merge milestone=`, never judged by the
    machine: the board records the answer, it does not decide it.
    """

    reviews: NotRequired[bool]
    """Cards planned into this chapter default to `review=True` unless the card
    says otherwise. A default, not a rule: the per-card flag always wins."""

    branch: str  # "ms/<slug>", computed ONCE at creation and STORED.
    #              Never re-derived from a mutable title (v1's ghost branches).
    status: str  # open | done | dropped
    created: float


class Event(TypedDict):
    id: str  # sha256(canonical)[:32]
    task: str  # never empty; "project" for board-level facts
    actor: str  # "dev:<x>" | "agent:<dev>/<x>" | "taskops"
    kind: str
    body: dict[str, Any]  # open: an unknown kind is stored intact
    ts: float


class Lease(TypedDict):
    """Lives in live.sqlite. Never enters the log, never replicates."""

    task: str  # PRIMARY KEY — the PK *is* the mutex
    actor: str
    branch: str  # "tk-<id>", stored at take, never re-derived
    acquired: float
    expires: float


CARD_STATUSES = ("open", "done", "dropped")  # stored
DERIVED_STATES = ("ready", "doing", "blocked", "stalled", "review", "reviewing", "changes")
MILESTONE_STATUSES = ("open", "done", "dropped")
CLOSED = ("done", "dropped")
LEASE_TTL = 900.0  # 15 min; every MCP call renews it
PROJECT = "project"  # the `task` of board-level events


class Kind(NamedTuple):
    replayed: bool  # does replay fold it into state, or is it history only?
    body_keys: tuple[str, ...]  # required keys; extras are allowed and kept


KINDS: dict[str, Kind] = {
    "created": Kind(True, ("card",)),
    "edited": Kind(True, ("field", "to")),
    "claimed": Kind(True, ("branch",)),
    "released": Kind(True, ("note",)),
    "status": Kind(True, ("to",)),
    "comment": Kind(False, ("text",)),
    "commit": Kind(False, ("sha", "subject")),
    "merged": Kind(False, ("into", "sha")),
    "milestone": Kind(True, ("op",)),
    # A fact about the REPO, not about any card: `task` is PROJECT and the fold
    # keeps the newest per `op`. Same shape as `milestone` on purpose — an `op`
    # is how a family of board-level facts grows without a new kind each time.
    "project": Kind(True, ("op",)),
    # Review is derived from the thread, exactly like a pending mention: both
    # kinds are history-only, and `core/review.py` folds them into a Standing.
    "submitted": Kind(False, ("note",)),  # the worker says it is finished
    "reviewed": Kind(False, ("verdict", "note")),  # verdict: "pass" | "changes"
}

# Fields of a Card that `edited` may target. Anything else is a BadRequest, so
# a typo cannot invent a column that only exists in one board's history.
EDITABLE = (
    "title",
    "spec",
    "criteria",
    "priority",
    "milestone",
    "parent",
    "after",
    "files",
    "labels",
    "assignee",
    "review",
)
LIST_FIELDS = ("after", "files", "labels", "criteria")  # edited as a whole list, never appended to
