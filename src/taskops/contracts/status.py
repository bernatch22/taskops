"""`taskops status` — the whole project in one screen, as a contract.

The shape of "where do things stand", assembled once so that the terminal, a prompt
segment and (one day) the studio all answer the question the same way. Everything here
is a COUNT or a short string: status is read in under a second and anything that needs
scrolling belongs to `board`, `fleet` or a dossier.

Nothing on this object is optional in the TypedDict sense — a caller must never branch
on a missing key — so the "not configured" cases are spelled as empty strings and zeros.
`objective` is the clearest example: the project's objective is a separate feature, and
until it lands every project has one that is empty and renders as nothing.
"""

from __future__ import annotations

from typing import TypedDict

__all__ = ["Claim", "Bottleneck", "Reports", "Sync", "Status"]


class Claim(TypedDict):
    """A live claim on a card, and how long it has left.

    ONE type for `mine` and for everybody else's, because they are the same fact and
    the only difference is whose `actor` it is. Two shapes would let the two lists
    drift, and the drift would land on the row that says somebody else is in my files.
    """

    actor: str
    task: str
    title: str
    state: str
    """The task's status. Spelled `state` because `status` is the name of the whole
    object here, and a `claim["status"]` inside a `Status` reads as a recursion."""

    left: float
    """Seconds until the lease expires. Negative never happens — an expired lease is
    not a live claim — but a claim about to lapse is the one worth colouring."""

    expiring: bool
    """`left` is under the warning threshold. Decided in the use case rather than in
    the renderer: two renderers must not be free to disagree about what "soon" is."""


class Bottleneck(TypedDict):
    """The one open card blocking the most others — the argument for doing it first."""

    task: str
    title: str
    blocks: int


class Reports(TypedDict):
    """Whether the write-up habit is being kept, in two facts and no prose."""

    today: str
    today_events: int
    yesterday: str
    yesterday_written: bool
    yesterday_narrated: bool
    """A dossier exists AND a model has written the prose section. Both are shown,
    because a generated file nobody narrated is a different kind of gap."""


class Sync(TypedDict):
    """This machine's standing against the one remote, or nothing when there is none."""

    host: str
    """The remote's hostname, never its URL and never its token. Empty = local only."""

    ahead: int
    """Local events the server has not been sent. The number that says `push`."""

    last_sync: float
    """When the cursor file was last written — the last push or pull. 0.0 for never."""


class Status(TypedDict):
    """Where the project stands, for the one command somebody types before working."""

    project: str
    root: str
    actor: str
    objective: str
    """The project's stated goal, or "" while that feature does not exist yet. An
    empty objective renders as NOTHING — never as an error and never as a placeholder."""

    total: int
    ready: int
    blocked: int
    counts: dict[str, int]
    mine: list[Claim]
    others: list[Claim]
    """Everybody else's live claims — the collision warning before it is a merge."""

    idle: int
    idle_days: int
    """How many open cards nobody has touched in `idle_days`, and the window itself —
    carried so the renderer never has to know the threshold to name it."""

    bottleneck: Bottleneck | None
    reports: Reports
    sync: Sync
